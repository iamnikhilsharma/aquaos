# TDD Evidence — Menu Bar & Control Center persisted prefs (task t_b8f3667f: Night Shift, input source, power mode)

Task: `t_b8f3667f` — "AquaOS: expand Top Menu Bar + Control Center controls" (second in the
2026-10-31 parity execution order; operator-approved scope from decision run `t_c3d567af`).

Source plan: no `*.plan.md` — user journeys were derived during this TDD run from the
operator-approved scope and ROADMAP catalog §1 / §3.B.

## User journeys

1. As a desktop user, I toggle Night Shift from the Control Center (or Settings → Displays)
   so evening use is easier on the eyes, and my choice survives a page reload.
2. As a desktop user, I switch my keyboard input source (US / International / Dvorak) in
   Settings → Keyboard & Gesture so the active layout is persisted system-wide.
3. As a desktop user, I pick a battery power mode (Automatic / Low Power / High Power) from
   Settings → Battery & Energy — or toggle Low Power Mode straight from the menu-bar battery
   popover — and the mode persists and re-syncs both surfaces.
4. On boot, the desktop restores Night Shift, input source, and power mode from the server's
   persisted settings instead of falling back to hardcoded UI state.

## Task report (RED → GREEN)

| # | Behavior | Result | Evidence |
|---|----------|--------|----------|
| 1 | RED validated before implementation | confirmed | `python tests/run_tests.py` → `Summary: 30 passed, 4 failed out of 34`: `test_prefs_defaults_and_validation`/`test_config_defaults_match_prefs_model` fail `No module named 'core.system_prefs'`; `test_system_prefs_routes_persist` fails on 404 (missing route); `test_menu_bar_control_center_persisted_prefs` fails on absent UI wiring. Commit `a89bd62`. |
| 2 | GREEN after minimal implementation | confirmed | Same runner → `Summary: 34 passed, 0 failed out of 34 tests`. Commit `740197d`. |
| 3 | Integration defect caught by TDD | fixed | First GREEN run exposed that `/api/settings/get` existed only as POST, so the new boot-time restore GET would 404. Fixed by adding the GET alias in `do_GET` (read=GET / write=POST); invalid control input → 400 `{"error": ...}`. |
| 4 | Live E2E on the real server (http://127.0.0.1:8765) | confirmed | Bundled-Chromium CDP driver (`cdp_prefs.mjs`): 15/15 checks — boot defaults, CC Night Shift click → POST persisted, reload → state restored, Dvorak switch → persisted + restored, power-mode select + menu-bar LPM toggle → persisted, machine left on defaults, 0 console/window errors. Screenshots: `cc-nightshift-on.png` (warm wallpaper), `cc-prefs-keyboard-pane.png` (Input Source card, US active). |

## Test specification

| # | What is guaranteed | Test / command | Type | Result |
|---|--------------------|----------------|------|--------|
| 1 | Input-source & power-mode accept canonical + case-insensitive forms only; Night Shift flag strictly boolean | `tests/test_system_prefs.py::test_prefs_defaults_and_validation` | unit | PASS |
| 2 | AquaConfig ships prefs defaults equal to the validation model | `tests/test_system_prefs.py::test_config_defaults_match_prefs_model` | unit | PASS |
| 3 | The three control endpoints canoncalize, persist to `settings.json`, reject unknown values with 400, and `settings/get` reads back | `tests/test_system_prefs.py::test_system_prefs_routes_persist` (real ThreadingHTTPServer on port 0) | integration | PASS |
| 4 | UI surfaces (CC button, Displays toggle, Keyboard pane, Battery select, battery-popover LPM) all route through the shared setters and post to the real endpoints; stale toast-only handlers removed; boot restore wired | `tests/test_desktop.py::test_menu_bar_control_center_persisted_prefs` | UI contract | PASS |
| 5 | Full suite regression | `python tests/run_tests.py` → 34/34 | suite | PASS |
| 6 | Live app behavior incl. persistence across real page reloads | `node cdp_prefs.mjs` → 15/15 | E2E (CDP) | PASS |

## Coverage & known gaps

- The repo's zero-dependency runner has no coverage tooling; 80%-coverage gate is not
  measurable here. Structural coverage by surface: validation model (unit), all 3 new
  routes (integration), all 5 UI touchpoints (contract), plus live E2E.
- Intentionally excluded from this card: True Tone, AirPlay mirroring, AirDrop, and
  Bluetooth battery levels remain cosmetic (recorded in ROADMAP §1 status).
- Not a defect introduced here but observed during security scan: the lock-screen dialog
  hardcodes demo password `aquaos` (desktop.html ~L1310, pre-existing).

## Merge evidence

Three checkpoints on `main` (no squash planned): RED `a89bd62`, GREEN `740197d`,
docs `bf38e3e`. Live-verification artifacts were captured from the restarted preview
server (PID 26712) so the operator's 8765 instance serves the new code.