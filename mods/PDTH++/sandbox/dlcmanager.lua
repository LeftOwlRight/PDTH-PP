--[[
PDTH++ 客户端协议标记注入。
复用原版加入请求必带的空格分隔 DLC 字符串追加 `pdthpp_protocol_N`，
因此即使其他模组替换了 ClientNetworkSession 的加入函数，只要仍调用 dlcs_string()，
PDTH++ 标记就会随请求发送。标记同时包含网络协议、游戏版本和模组发布版本。
]]

local module = ... or D:module("PDTH++")
local GenericDLCManager = module:hook_class("GenericDLCManager")

-- Replace stale/duplicate synthetic markers, keeping legitimate DLCs intact.
module:hook(GenericDLCManager, "dlcs_string", function(self)
	local dlcs = module:call_orig(GenericDLCManager, "dlcs_string", self) or ""
	local _, _, cleaned = module:pdthpp_clean_protocol_tokens(dlcs)
	local token = module:pdthpp_protocol_token()
	if not token then
		return cleaned
	end
	return cleaned == "" and token or cleaned .. " " .. token
end, true)
