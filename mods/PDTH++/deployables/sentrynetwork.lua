local module = ... or D:module("PDTH++")
local RETRY_INTERVAL, CANCEL_AFTER = 1, 8
local RESULT_CACHE_SIZE = 16

local function clock()
	return Application:time()
end

local function peer_key(peer)
	return tostring(peer:user_id() or peer:id())
end

local function integer(value)
	return type(value) == "number" and value >= 0 and value < 2147483647 and value == math.floor(value)
end

local function clear_interaction(pending)
	if alive(pending.unit) then
		local interaction = pending.unit:interaction()
		if interaction then interaction._pdthpp_pickup_requested = nil end
	end
end


function module:pdthpp_reset_sentry_runtime()
	local pending = self._pdthpp_sentry_pickup
	if pending then clear_interaction(pending) end
	if pending and not pending.committed and self.pdthpp_refund_sentry_pickup then
		self:pdthpp_refund_sentry_pickup(pending.plan)
	end
	self._pdthpp_sentry_pickup = nil
	self._pdthpp_sentry_status_cache = {}
	self._pdthpp_sentry_status_request_times = {}
	self._pdthpp_sentry_status_peer_times = {}
	self._pdthpp_sentry_receipts = {}
	self._pdthpp_sentry_sequence = 0
	self._pdthpp_sentry_instance_sequence = 0
	self._pdthpp_sentry_query_sequence = 0
	self._pdthpp_next_status_cleanup = nil
	self._pdthpp_sentry_epoch = tostring(clock()) .. ":" .. tostring(math.random(1, 1000000000))
end

function module:pdthpp_sentry_instance(unit)
	local base = alive(unit) and unit:base()
	if not base then return nil end
	if Network:is_server() and not base._pdthpp_instance then
		self._pdthpp_sentry_instance_sequence = self._pdthpp_sentry_instance_sequence + 1
		base._pdthpp_instance = self._pdthpp_sentry_epoch .. ":" .. self._pdthpp_sentry_instance_sequence
	end
	return base._pdthpp_instance
end

function module:pdthpp_forget_sentry(unit)
	local id = unit:id()
	local cached = self._pdthpp_sentry_status_cache[id]
	local request = self._pdthpp_sentry_status_request_times[id]
	if cached and cached.unit == unit then self._pdthpp_sentry_status_cache[id] = nil end
	if request and request.unit == unit then self._pdthpp_sentry_status_request_times[id] = nil end
	-- Pending payments and receipts outlive the unit: destruction can arrive
	-- before its transaction result. Only a matching result may settle payment.
end

function module:pdthpp_sentry_pickup_pending()
	return self._pdthpp_sentry_pickup ~= nil
end


function module:pdthpp_begin_sentry_pickup(unit, plan)
	local session = managers.network and managers.network:session()
	local server = session and session:server_peer()
	local id = self:pdthpp_sentry_unit_key(unit)
	local instance = self:pdthpp_sentry_instance(unit)
	if self:pdthpp_sentry_pickup_pending() or not server or not id or not instance
		or not self:pdthpp_has_local_sentry_equipment_space()
		or not self:pdthpp_apply_sentry_pickup_cost_plan(plan) then
		return false
	end
	self._pdthpp_sentry_sequence = self._pdthpp_sentry_sequence + 1
	local data = { module = self:id(), epoch = self._pdthpp_sentry_epoch,
		request_id = self._pdthpp_sentry_sequence, unit_id = id, instance = instance }
	local pending = { data = data, plan = plan, unit = unit, started = clock(), last_send = clock() }
	self._pdthpp_sentry_pickup = pending
	local interaction = unit:interaction()
	if interaction then interaction._pdthpp_pickup_requested = true end
	-- Payment is escrowed now; firing/changing weapons during the roundtrip can
	-- no longer make a successful response fail to pay after the gun is deleted.
	if not DNet:send_to_peer(server, "PDTHPPSentryPickupRequest", data, false, false) then
		self:pdthpp_refund_sentry_pickup(plan)
		clear_interaction(pending)
		self._pdthpp_sentry_pickup = nil
		return false
	end
	return true
end

function module:pdthpp_can_pickup_sentry(peer, unit)
	if not peer or not alive(unit) or self:pdthpp_sentry_owner_peer_id(unit) ~= peer:id() then
		return false
	end
	local base = unit:base()
	if not base or not base.destroy_sentry or base._pdthpp_pickup_in_progress then return false end
	local game = managers.network and managers.network:game()
	local player = peer:is_local_user() and managers.player:player_unit()
		or game and game:unit_from_peer_id(peer:id())
	if not alive(player) then return false end
	local damage = player:character_damage()
	if damage and damage:dead() then return false end
	local tweak = tweak_data.interaction.sentry_gun
	local distance = (tweak and tweak.interact_distance or 200) + 100
	return mvector3.distance(player:position(), unit:position()) <= distance
end

local function result_from(data)
	return { module = module:id(), epoch = data.epoch, request_id = data.request_id,
		unit_id = data.unit_id, instance = data.instance, success = false }
end

function module:pdthpp_receive_pickup_request(peer, data, cancel)
	if not integer(data.request_id) or data.request_id == 0 or not integer(data.unit_id)
		or type(data.epoch) ~= "string" or #data.epoch > 80
		or type(data.instance) ~= "string" or #data.instance > 100 then return end
	local key = peer_key(peer)
	local bucket = self._pdthpp_sentry_receipts[key]
	if not bucket then
		bucket = { epoch = data.epoch, highest = 0, results = {}, order = {} }
		self._pdthpp_sentry_receipts[key] = bucket
	end
	local result = bucket.results[data.request_id]
	if bucket.epoch ~= data.epoch then
		result = result_from(data)
	elseif data.request_id <= bucket.highest then
		-- An evicted/older request is never executed again. Only one request is
		-- outstanding per client, so its success receipt cannot be evicted by it.
		result = result or result_from(data)
	else
		bucket.highest = data.request_id
		result = result_from(data)
		bucket.results[data.request_id] = result
		bucket.order[#bucket.order + 1] = data.request_id
		if #bucket.order > RESULT_CACHE_SIZE then
			bucket.results[table.remove(bucket.order, 1)] = nil
		end
		if not cancel then
			local unit = self:pdthpp_find_sentry_by_id(data.unit_id)
			if self:pdthpp_can_pickup_sentry(peer, unit)
				and self:pdthpp_sentry_instance(unit) == data.instance then
				unit:base()._pdthpp_pickup_in_progress = true
				result.success = self:pdthpp_destroy_sentry_exact(unit)
				if result.success then
					DNet:send_to_peers("PDTHPPSentryDestroyed", {
						module = self:id(), unit_id = data.unit_id, instance = data.instance,
					}, false, true)
				end
			end
		end
	end
	-- Keep the receipt even if sending fails. Retrying the same request or a
	-- cancellation obtains the authoritative outcome without a second destroy.
	DNet:send_to_peer(peer, "PDTHPPSentryPickupResult", result, false, false)
end

function module:pdthpp_settle_sentry_pickup()
	local pending = self._pdthpp_sentry_pickup
	if pending and pending.committed and self:pdthpp_add_local_sentry_equipment() then
		clear_interaction(pending)
		self._pdthpp_sentry_pickup = nil
		return true
	end
	return false
end

function module:pdthpp_receive_pickup_result(data)
	local pending = self._pdthpp_sentry_pickup
	if not pending then return end
	for _, key in ipairs({ "epoch", "request_id", "unit_id", "instance" }) do
		if pending.data[key] ~= data[key] then return end
	end
	if data.success == true then
		pending.committed = true
		if alive(pending.unit) and self:pdthpp_sentry_instance(pending.unit) == data.instance then
			self:pdthpp_destroy_sentry_exact(pending.unit)
		end
		self:pdthpp_settle_sentry_pickup()
	elseif data.success == false and not pending.committed then
		self:pdthpp_refund_sentry_pickup(pending.plan)
		clear_interaction(pending)
		self._pdthpp_sentry_pickup = nil
		if managers.hud then
			managers.hud:show_hint({ text = managers.localization:text("pdthpp_sentry_pickup_failed") })
		end
	end
end

function module:pdthpp_handle_sentry_network(peer, kind, data)
	if type(data) ~= "table" or data.module ~= self:id() or not peer then return end
	if Network:is_server() then
		if peer:is_local_user() then return end
		if kind == "PDTHPPSentryPickupRequest" or kind == "PDTHPPSentryPickupCancel" then
			self:pdthpp_receive_pickup_request(peer, data, kind == "PDTHPPSentryPickupCancel")
		elseif kind == "PDTHPPSentryStatusRequest" and integer(data.unit_id) then
			local key, t = peer_key(peer), clock()
			local limits = self._pdthpp_sentry_status_peer_times[key] or { units = {} }
			self._pdthpp_sentry_status_peer_times[key] = limits
			if limits.t and t - limits.t < 0.25
				or limits.units[data.unit_id] and t - limits.units[data.unit_id] < 1 then return end
			limits.t, limits.units[data.unit_id] = t, t
			local unit = self:pdthpp_find_sentry_by_id(data.unit_id)
			if type(data.query) ~= "string" or #data.query > 100 then return end
			if alive(unit) then
				self:pdthpp_send_sentry_status_to_peer(unit, peer, data.query)
			else
				DNet:send_to_peer(peer, "PDTHPPSentryMissing", {
					module = self:id(), unit_id = data.unit_id, query = data.query,
				}, false, false)
			end
		end
	elseif peer:is_server() then
		if kind == "PDTHPPSentryPickupResult" then
			self:pdthpp_receive_pickup_result(data)
		elseif kind == "PDTHPPSentryStatus" and integer(data.unit_id) then
			self:pdthpp_apply_remote_sentry_status(data)
		elseif kind == "PDTHPPSentryDestroyed" and integer(data.unit_id) then
			local unit = self:pdthpp_find_sentry_by_id(data.unit_id)
			if alive(unit) and self:pdthpp_sentry_instance(unit) == data.instance then
				self:pdthpp_destroy_sentry_exact(unit)
			end
		elseif kind == "PDTHPPSentryMissing" and integer(data.unit_id) then
			local unit = self:pdthpp_find_sentry_by_id(data.unit_id)
			if alive(unit) and type(data.query) == "string"
				and unit:base()._pdthpp_status_query == data.query then
				self:pdthpp_destroy_sentry_exact(unit)
			end
		end
	end
end

function module:pdthpp_update_sentry_network()
	local pending, t = self._pdthpp_sentry_pickup, clock()
	if pending then
		if pending.committed then
			self:pdthpp_settle_sentry_pickup()
		elseif t - pending.last_send >= RETRY_INTERVAL then
			local session = managers.network and managers.network:session()
			local server = session and session:server_peer()
			if not server then
				self:pdthpp_reset_sentry_runtime()
				return
			end
			pending.last_send = t
			local cancel = t - pending.started >= CANCEL_AFTER
			DNet:send_to_peer(server, cancel and "PDTHPPSentryPickupCancel" or "PDTHPPSentryPickupRequest",
				pending.data, false, false)
			-- Never refund an ambiguous timeout: the host may already have committed.
			-- Cancel is idempotent and returns success if commit won the race.
			if cancel and not pending.warned and managers.hud then
				pending.warned = true
				managers.hud:show_hint({ text = managers.localization:text("pdthpp_sentry_pickup_waiting") })
			end
		end
	end
	for id, request in pairs(self._pdthpp_sentry_status_request_times) do
		if not alive(request.unit) then
			self._pdthpp_sentry_status_request_times[id] = nil
		elseif request.attempts < 3 and t - request.t >= 1 then
			self:pdthpp_request_exact_sentry_status(request.unit, false)
		end
	end
	if not self._pdthpp_next_status_cleanup or t >= self._pdthpp_next_status_cleanup then
		self._pdthpp_next_status_cleanup = t + 1
		for _, limits in pairs(self._pdthpp_sentry_status_peer_times) do
			for id, last in pairs(limits.units) do
				if t - last >= 5 then limits.units[id] = nil end
			end
		end
	end
end

module:pdthpp_reset_sentry_runtime()
for _, event in ipairs({ "OnLoadLevel", "OnExitedLobby", "OnSessionCreated" }) do
	module:hook(event, "PDTHPP_SentryReset", function()
		module:pdthpp_reset_sentry_runtime()
	end)
end
module:hook("OnPeerRemoved", "PDTHPP_SentryPeerRemoved", function(peer)
	if not peer then return end
	module._pdthpp_sentry_receipts[peer_key(peer)] = nil
	module._pdthpp_sentry_status_peer_times[peer_key(peer)] = nil
	if not Network:is_server() and peer:is_server() then module:pdthpp_reset_sentry_runtime() end
end)
