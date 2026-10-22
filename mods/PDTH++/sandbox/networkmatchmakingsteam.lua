--[[
Steam 大厅发现阶段的 PDTH++ 兼容标签。
该标签无论“联机隔离”设置是否开启都保留，用于大厅列表提前过滤和标识协议版本；
设置开关只影响主机收到实际连接请求后是否强制拒绝无模组玩家。
]]

local module = ... or D:module("PDTH++")
local NetworkMatchMakingSTEAM = module:hook_class("NetworkMatchMakingSTEAM")

-- Always keep the PDTH++ protocol tag on lobby discovery, even when the host
-- disables forced join rejection in the mod options. Minor releases can remain
-- compatible while this protocol stays unchanged.
-- Keep the game's own version boundary, including on repeated script loads.
module._pdthpp_game_build = module._pdthpp_game_build or NetworkMatchMakingSTEAM._BUILD_SEARCH_INTEREST_KEY
NetworkMatchMakingSTEAM._BUILD_SEARCH_INTEREST_KEY = string.format(
	"%s-%s-protocol-%s",
	module:pdthpp_game_build(),
	module:id(),
	module.PDTHPP_NETWORK_PROTOCOL
)
