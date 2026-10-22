# PDTH++ — development branch

This gameplay overhaul changes weapons, enemies and deployables. Development
features may change and require compatible PDTH++ peers for multiplayer.

## Requirements and installation

- PAYDAY: The Heist Update 23.
- Current dahm framework and hook (tested against the 1.18.1.1 Lua framework).
- Copy `mods/PDTH++` into the game's `mods` directory, backing up an existing
  installation first. Keep personal dahm configuration outside bundled mod files.

Update 23 provides `DB:create_entry` and mod_overrides support. An old standalone
PDTHModOverrides DLL is no longer a required dependency on that game version.
Use the new dahm hook; do not combine it with the old lightfx injector. See the
[dahm author's upgrade instructions](https://steamcommunity.com/groups/dahm4pd/announcements/detail/703282384630450510).

## Multiplayer compatibility

Lobby discovery and host admission use the game's network build plus the shared
PDTH++ wire protocol in `sandbox/networkcompat.lua`. **PDTH++ release/version
numbers may differ and are never compared for admission.** Only incompatible
game builds or wire protocols require matching/updating.

The current protocol is **2**, introducing transactional sentry recovery. Older
builds that send their release number as their protocol do not implement that
message format and must update. Future text, balance or bug-fix releases that
keep protocol 2 and its compatible units/messages can play together.

Host-side online isolation is enabled by default. Disabling that option allows
unmarked clients through the host check, while the distinct lobby search key
remains active. The option protects PDTH++ hosts; it is not anti-cheat attestation
or a ban on other mods. Modified clients cannot make an unmodified game display
custom rejection text; clients with this build show the specific reason when
receiving a tagged host rejection.

## Sentry stability and recovery

- Missed shots after a hitch are discarded, on both host and clients, preventing
  a burst of impacts and sound when the frame rate recovers. Normal frame rounding
  still preserves the configured fire rate.
- Recovery cost is quoted when the hold interaction begins. Cancelling the hold
  costs nothing. Completing it escrows ammunition before sending a request, so
  later weapon/ammo changes cannot invalidate a successful recovery response.
- The host validates owner, player state, distance and sentry incarnation, then
  records a replayable result. Duplicate requests cannot recover a gun twice.
- A rejected/cancelled recovery refunds escrow. After an ambiguous timeout the
  client requests cancellation and waits for the host's definitive result rather
  than refunding a transaction that may already have succeeded. Leaving the
  session clears outstanding state. A fully unresponsive host cannot be resolved
  locally without risking duplication; its pending cancellation remains visible.
- Sentry status uses instance/query identifiers and revisions to reject stale
  data. Requests and retries are limited, and temporary state is cleared on level
  changes, unit destruction and peer removal.

Detailed sentry logging is off by default. To diagnose an issue, add
`pdthpp_sentry_diagnostics = true` to the existing config table in dahm's
`mods/user.lua`, then restart. Diagnostics write `[SENTRY-DIAG]` to `logs/main.log`.

## Verification

`tests/offline.py` exercises the unchanged game weapon functions through dahm's
real object-hook wrapper, and simulates separate host/client runtimes for message
loss, cancellation and replay. It requires Python and `lupa` with LuaJIT support,
plus sibling `pdth-source` and `dahm/release-20261020` references. Override their
locations with `PDTH_SOURCE` and `DAHM_CORE` if needed:

```text
python tests/offline.py
```

These tests do not launch the game. Real asset loading, physics, audio and Steam
multiplayer still require in-game verification. See [the manual test plan](docs/manual-testing.md).
