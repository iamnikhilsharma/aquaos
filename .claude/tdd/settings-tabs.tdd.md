# TDD Evidence — System Settings preference tabs (task t_558aae60: connectivity, notifications, focus, storage, sharing)

Task: `t_558aae60` — "AquaOS: expand System Settings preference tabs" (third and last in the
2026-10-31 parity execution order; operator-approved scope from decision run `t_c3d567af`).

Source plan: no `*.plan.md` — user journeys were derived during this TDD run from the card
scope and ROADMAP catalog §3.A/§3.B/§3.C.

## User journeys

1. As a desktop user, I open System Settings → Notifications (or Focus / Storage / AirDrop &
   Sharing) and every switch I flip survives a page reload and a server restart.
2. As a desktop user, I open the Wi-Fi & Network pane and see live connection state (real
   SSID, powered state from `/api/system/status`) instead of the old hardcoded fake IP card,
   and my Private-MAC / firewall / stealth choices persist.
3. As a desktop user, I pick a Focus profile or toggle Do Not Disturb from either the pane or
   the Control Center — both surfaces reflect the same persisted state.
4. As a desktop user, the Storage pane shows a color-coded breakdown with real disk totals,
   real per-directory sizes, and real largest files (no fake catalog), refreshable.
5. As a desktop user, invalid state can never reach the persistence layer: the backend
   rejects unknown values/types with HTTP 400.

## Task report (RED → GREEN)

| # | Behavior | Result | Evidence |
|---|----------|--------|----------|
| 1 | RED validated before implementation | confirmed | `python tests/run_tests.py` → `Summary: 33 passed, 4 failed out of 37`: `test_prefs_defaults_and_validation` fails on `No module named`-style import of the new normalizers; `test_settings_tabs_routes_persist` fails on the unvalidated/never-persisting toggle route; `test_storage_usage_route` fails on 404 (missing route); `test_settings_panes_persisted_parity` fails on missing sidebar panes. Commit `303c451`. |
| 2 | GREEN after implementation | confirmed | Same runner → `Summary: 37 passed, 0 failed out of 37 tests`. Commit `2eb443c`. |
| 3 | Integration defects caught by TDD | fixed | (a) `_canonical` matched only exact casefolded values, so canonical macOS spellings ("By App", "Wi-Fi") were rejected — separator-collapsed matching added in `core/system_prefs.py`; (b) the notifications route fed the whole body through the strict-boolean payload validator and 400'd on `grouping` — split bool-field/key normalization; (c) the shared test harness `_load_server_module()` left the cached server module pointing at the first test's temp config dir — it now re-binds `config` and re-hydrates per call. |
| 4 | Live E2E on the real server (http://127.0.0.1:8765) | confirmed | Bundled-Chromium CDP driver (`cdp_settings.mjs`): 21/21 checks — 4 panes present in macOS sidebar order with correct badges; no hardcoded IP anywhere in the network pane; every new control POSTs, persists to `settings.json`, and is restored across a real page reload (sleep-on, badges-off, by_app, DND-on, Work, airdrop-everyone); CC Focus/AirDrop share the same persisted state; Storage pane renders 8 real categories (aqua-desktop 1.4 GB / 67.3%) + largest-files from the live endpoint; Sound slider round-trips 42 → server; machine returned to defaults; 0 console/window errors. Screenshots: `settings-storage-pane.png` (color-coded bar + legend + largest files), `settings-sharing-pane.png` (AirDrop select + four service toggles), `settings-notifications-pane.png` (captured the Sharing pane state during phase A — notifications pane state proven by A1/C1/H1 checks). |

## Test specification

| # | What is guaranteed | Test file or command | Test type | Result |
|---|--------------------|----------------------|-----------|--------|
| 1 | Toggle/notification/focus/airdrop/sharing/firewall values accept canonical + case-insensitive + separator-flexible forms only; booleans are strict | `tests/test_system_prefs.py::test_prefs_defaults_and_validation` | unit | PASS |
| 2 | Pref defaults merge into AquaConfig section-by-key — pre-existing sections (security.mode, ai.provider…) survive | `tests/test_system_prefs.py::test_config_defaults_match_prefs_model` | unit | PASS |
| 3 | The 6 control endpoints canonicalize, persist to `settings.json`, reject unknown values with 400, and `/api/system/toggle` (wifi/bt/dnd) is now persisted + reflected in `/api/system/status` | `tests/test_system_prefs.py::test_settings_tabs_routes_persist` (real ThreadingHTTPServer on port 0) | integration | PASS |
| 4 | `GET /api/storage/usage` serves real disk totals + bounded real per-directory breakdown + largest files, sorted, never negative | `tests/test_system_prefs.py::test_storage_usage_route` | integration | PASS |
| 5 | UI contract: Notifications/Focus/Storage/Sharing panes + live Network pane + Sound slider all wired to the real endpoints; stale cosmetic handlers (`toggleWifi(el)`, hardcoded IP) removed; boot restore wired | `tests/test_desktop.py::test_settings_panes_persisted_parity` | UI contract | PASS |
| 6 | Full suite regression (34 pre-existing + 3 new) | `python tests/run_tests.py` → 37/37 | suite | PASS |
| 7 | Live app behavior incl. persistence across real page reloads + restart hydration path | `node cdp_settings.mjs` → 21/21 | E2E (CDP) | PASS |

## Coverage & known gaps

- The repo's zero-dependency runner has no coverage tooling; the 80%-coverage gate is not
  measurable here. Structural coverage by surface: full validation model (unit), all 7
  touched/new routes (integration), all UI touchpoints (contract), plus live E2E.
- Intentionally excluded from this card (documented in ROADMAP §1 action plan): keyboard
  repeat sliders, trackpad gesture toggles, dock tiling switches, display-sleep select,
  alert-sound select, optimized-battery-charging toggle, and default-app selects remain
  cosmetic (`showToast`) — each is small, but they belong to panes outside the approved
  connectivity/notifications/focus/storage/sharing scope.
- Not a defect introduced here but observed during the prior card's security scan: the
  lock-screen dialog hardcodes demo password `aquaos` (desktop.html ~L1310, pre-existing).
- Storage breakdown walks the AquaOS project root (real sizes); a full system-volume
  category taxonomy (Apps vs Documents vs System Data) would need a fixed Linux rootfs
  mount map — deferred with the file-sharing/AirDrop runtime daemons.

## Merge evidence

Three checkpoints on `main` (no squash planned): RED `303c451`, GREEN `2eb443c`,
docs (this report + ROADMAP). Live-verification artifacts were captured from the restarted
preview server so the operator's 8765 instance serves the new code.