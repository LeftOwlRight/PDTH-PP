--[[
PDTH++ 主机侧联机隔离。
客户端把协议标记附加在原版 DLC 字符串中；主机在创建 NetworkPeer 之前校验，
开启“联机隔离”时拒绝缺失或协议不匹配的客户端。校验后无论开关都移除伪 DLC 标记，
避免污染原版 DLC 权限和玩家资料。这里只验证 PDTH++ 本身，不限制 DAHM 或其他加载器。
]]

local module = ... or D:module("PDTH++")
local ConnectionNetworkHandler = module:hook_class("ConnectionNetworkHandler")

-- 旧配置中不存在该选项时默认开启，以保持首次加入此功能版本时的隔离行为。
local function network_isolation_enabled()
	local enabled = D:conf("network_isolation")

	-- Preserve Test 8 behaviour for existing configurations which do not yet
	-- contain this newly added option.
	if enabled == nil then
		return true
	end

	return enabled ~= false
end

-- 在玩家 Peer 尚未创建时使用原版拒绝回复，避免出现“先加入房间再被踢”的中间状态。
local function reject_incompatible_join(peer_name, sender, reason)
	local session = managers.network and managers.network:session()
	local local_peer = session and session:local_peer()
	local my_user_id = local_peer and local_peer:user_id() or ""

	module:log(2, "ConnectionNetworkHandler:request_join",
		"Rejected incompatible peer:", tostring(peer_name), tostring(reason),
		sender and sender:ip_at_index(0) or "unknown"
	)

	if sender then
		-- Reply 2 is the vanilla rejected/kicked response. No peer has been created yet.
		sender:join_request_reply(2, 0, 1, 1, 0, "pdthpp_reject_" .. reason, my_user_id)
	end
end

-- 最早的加入请求入口，可覆盖大厅、好友邀请、中途加入和直接连接等路径。
module:hook(ConnectionNetworkHandler, "request_join", function(self, peer_name, mask_set, dlcs, client_ip, client_user_id, host_user_id, sender)
	-- Preserve the vanilla early validation before responding to arbitrary packets.
	if not self:_verify_in_server_session() then
		return
	end

	if SystemInfo:platform() == Idstring("WIN32") and Steam:userid() ~= host_user_id then
		print("[PDTH++ ConnectionNetworkHandler:request_join] wrong host_user_id", host_user_id)
		return
	end

	local valid_protocol, reason, cleaned_dlcs = module:pdthpp_clean_protocol_tokens(dlcs)
	if network_isolation_enabled() and not valid_protocol then
		reject_incompatible_join(
			peer_name,
			sender,
			reason
		)
		return
	end

	-- Always strip the synthetic marker before vanilla DLC ownership logic or
	-- storing it in NetworkPeer's DLC list. The lobby protocol tag remains
	-- active regardless of this host-side option.
	return module:call_orig(
		ConnectionNetworkHandler,
		"request_join",
		self,
		peer_name,
		mask_set,
		cleaned_dlcs,
		client_ip,
		client_user_id,
		host_user_id,
		sender
	)
end, true)

-- Store the rejection only around the synchronous vanilla callback. Arbitrary
-- senders must not be able to leave a stale reason for an unrelated kick dialog.
module:hook(ConnectionNetworkHandler, "join_request_reply", function(self, reply, id, level, difficulty, state, mask, user_id, sender)
	local session = managers.network and managers.network:session()
	local server = session and session:server_peer()
	local reason = type(mask) == "string" and mask:match("^pdthpp_reject_(%a+)$")
	if reply == 2 and server and user_id == server:user_id()
		and (not server:ip() or sender:ip_at_index(0) == server:ip())
		and (reason == "missing" or reason == "protocol" or reason == "game") then
		module._pdthpp_join_rejection = { reason = reason, t = Application:time() }
	end
	local result = module:call_orig(ConnectionNetworkHandler, "join_request_reply", self,
		reply, id, level, difficulty, state, mask, user_id, sender)
	module._pdthpp_join_rejection = nil
	return result
end, true)
