local module = ... or D:module("PDTH++")

-- Wire compatibility, NOT the release/version number. Only change this when
-- peers cannot safely interpret each other's units or network messages.
-- Protocol 2 introduces instance-bound, idempotent sentry pickup transactions.
module.PDTHPP_NETWORK_PROTOCOL = "2"
module.PDTHPP_PROTOCOL_PREFIX = "pdthpp_protocol_"

function module:pdthpp_game_build()
	return self._pdthpp_game_build
end

function module:pdthpp_protocol_token()
	local build = self:pdthpp_game_build()
	return build and self.PDTHPP_PROTOCOL_PREFIX .. self.PDTHPP_NETWORK_PROTOCOL .. "-game-" .. build
end

function module:pdthpp_clean_protocol_tokens(dlcs)
	local cleaned, markers = {}, {}
	for token in string.gmatch(type(dlcs) == "string" and dlcs or "", "%S+") do
		if token:sub(1, #self.PDTHPP_PROTOCOL_PREFIX) == self.PDTHPP_PROTOCOL_PREFIX then
			markers[#markers + 1] = token
		else
			cleaned[#cleaned + 1] = token
		end
	end
	local expected = self:pdthpp_protocol_token()
	local valid = expected ~= nil and #markers > 0
	for _, token in ipairs(markers) do
		valid = valid and token == expected
	end
	local reason = #markers == 0 and "missing" or "protocol"
	if #markers == 1 then
		local protocol, build = markers[1]:match("^pdthpp_protocol_([%w.]+)%-game%-([%w.]+)$")
		if protocol == self.PDTHPP_NETWORK_PROTOCOL and build ~= self:pdthpp_game_build() then
			reason = "game"
		end
	end
	return valid, reason, table.concat(cleaned, " ")
end
