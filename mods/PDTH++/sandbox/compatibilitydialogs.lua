local module = ... or D:module("PDTH++")
local MenuManager = module:hook_class("MenuManager")

module:hook(MenuManager, "show_peer_kicked_dialog", function(self, ...)
	local reason = module._pdthpp_join_rejection
	module._pdthpp_join_rejection = nil
	if reason and Application:time() - reason.t < 5 then
		managers.system_menu:show({
			title = managers.localization:text("pdthpp_join_incompatible_title"),
			text = managers.localization:text("pdthpp_join_incompatible_" .. reason.reason),
			button_list = { { text = managers.localization:text("dialog_ok") } },
		})
		return
	end
	return module:call_orig(MenuManager, "show_peer_kicked_dialog", self, ...)
end, false)
