local module = ... or D:module("PDTH++")
local GameSetup = module:hook_class("GameSetup")

-- Runs even with no active sentry brain (empty/destroyed gun, reply in flight).
module:post_hook(GameSetup, "update", function(self, t, dt)
	module:pdthpp_update_sentry_network()
end, false)
module:post_hook(GameSetup, "paused_update", function(self, t, dt)
	module:pdthpp_update_sentry_network()
end, false)
