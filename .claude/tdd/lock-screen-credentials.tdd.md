# TDD Evidence — Lock-screen credential flow (task t_6d5bdf67)

Task: `t_6d5bdf67` — "Replace hardcoded demo password in lock-screen dialog with real
credential flow" (found by a Menu Bar/CC review run on 2026-10-31).

Source plan: no `*.plan.md` — journeys were derived during this TDD run from the task
body and the verified defect in `aqua-desktop/ui/desktop.html`.

## Defect (verified pre-change)

1. `desktop.html:L1310` shipped a prefilled demo credential (`value="aquaos"`) on the
   lock-screen password input.
2. `unlockScreen()` hid the overlay without verifying anything.
3. The global `keydown` handler unlocked the session on **any** key press while the lock
   screen was up (`if (lock-screen).display === 'flex') { unlockScreen(); }`) — so the
   gate was decorative even ignoring the demo password.

## Design decisions (2026-10-31)

- Credentials persist ONLY as salted PBKDF2-HMAC-SHA256 records (`core/credential_store.py`)
  in a dedicated `~/.config/aquaos/credentials.json`. NOT in `AquaConfig`: `config.as_dict()`
  is serialized verbatim by `/api/state` and `/api/settings/get`, so a hash in `settings.json`
  would be exposed to any local client. Atomic writes + best-effort `chmod 0600`.
- 600,000 iterations (OWASP 2023 rec for PBKDF2-HMAC-SHA256); 16-byte per-set random salt;
  passwords validated 6-72 chars, exact bytes preserved (no trimming).
- New routes: `GET /api/system/lock` (boolean only), `POST /api/system/password`
  (first-run setup; rotation requires `current_password` -> 401 otherwise),
  `POST /api/system/unlock` (401 on wrong password). No endpoint ever returns hash material.
- UI: first-run setup mode (password + confirm) when no credential is armed; password
  verification mode otherwise. Wrong attempts shake + inline error. Cancel/Esc cannot
  bypass an armed gate; the keydown bypass is dead (locked overlay swallows shortcuts).
- Auth calls use raw `fetch(API_BASE + ...)`, NOT `apiFetch` — its silent
  `localOSDispatch` fallback could fake an unlock when the backend is down (fail-closed).

## User journeys

1. As a first-run desktop user, I am asked to set (and confirm) a password when I lock
   the session, so my next lock is protected by a credential that lives only as a hash.
2. As a returning desktop user, I must type the correct password to unlock; a wrong or
   empty attempt shakes, shows an error, and keeps the session locked.
3. As a desktop user, I cannot bypass an armed gate via Cancel/Esc, the → button, or any
   stray keypress — only a correct password unlocks.
4. As a security reviewer, I can grep `desktop.html` and the persisted config and find no
   plaintext password and no exposed hash.

## Task report (RED → GREEN)

| # | Behavior | Result | Evidence |
|---|----------|--------|----------|
| 1 | RED validated before implementation | confirmed | `.venv/Scripts/python.exe -m pytest tests/test_credential_flow.py` → `6 failed in 0.24s`: 2 HTML-contract failures on the real defect (`'value="aquaos"' is contained here: ... value="aquaos"`), 4 on the missing implementation (`ModuleNotFoundError: No module named 'core.credential_store'`, absent routes). Commit `f042ca1`. |
| 2 | GREEN after minimal implementation | confirmed | Same file → `6 passed in 5.38s`; full suite `43 passed in 8.84s` (was 37 before). Repo's own runner `python tests/run_tests.py` → `43 passed, 0 failed out of 43`. Commit `ba4fbc6`. |
| 3 | Tests caught a design error | fixed | First GREEN run failed on the injected-iteration floor (10k) blocking fast test hashing; floor widened to 100 with the OWASP 600k default kept for real sets. |
| 4 | Rotation & replay | covered | Route test rotates the credential with the current password (401 without/with-wrong current) and proves the old password stops verifying. |
| 5 | Live E2E on an ISOLATED server (port 8755, scratch `AQUAOS_CONFIG_DIR`) | confirmed | Bundled-Chromium CDP drive of the real UI: first-run setup → persisted (`has_password: true`), toast "Password Saved — Session Secured"; reload → verify mode; wrong pw → "Incorrect password" + shake + stays locked; Esc → "Password required to unlock" (no bypass); random key → stays locked (old bypass dead); correct pw → "Unlocked AquaOS Session". 13 windows + 15 dock items intact, no layout damage. Screenshots captured at each stage. |
| 6 | A second layout defect caught only visually | fixed | The two-line setup hint wrapped under the Cancel/Switch User pills at short viewports → shortened the copy and reserved 96px bottom padding on the overlay (setup clears by 21px, verify by 41px at a 430px-tall viewport). Commit `174f8e4`. |

## Test specification

| # | What is guaranteed | Test / command | Type | Result |
|---|--------------------|----------------|------|--------|
| 1 | No `value="aquaos"` anywhere in UI source; no password-type input carries a prefilled value; `unlockScreen` gone; keydown bypass gone | `tests/test_credential_flow.py::test_lock_screen_has_no_plaintext_demo_password` | UI contract | PASS |
| 2 | First-run setup + verify markup/functions wired; Enter/arrow/cancel routed through the real flow; raw-fetch endpoints present; shake animation present | `tests/test_credential_flow.py::test_lock_screen_first_run_and_verify_flow_is_wired` | UI contract | PASS |
| 3 | PBKDF2 round-trip verifies right/rejects wrong; per-set salts differ; persisted record carries only derived material (no plaintext) | `tests/test_credential_flow.py::test_credential_hash_round_trip_and_salt_uniqueness` | unit | PASS |
| 4 | Password validation rejects non-string/short/long, returns exact bytes; malformed stored credentials never match (md5 algorithm, missing keys, non-hex, out-of-range iterations) | `tests/test_credential_flow.py::test_password_validation_and_malformed_credentials` | unit | PASS |
| 5 | Live routes: fresh `has_password:false` → setup persists hash-only on disk → status exposes only the boolean → wrong unlock 401 / right unlock 200 → rotation requires current password → old credential stops verifying | `tests/test_credential_flow.py::test_lock_routes_setup_verify_rotation_and_persist` (real ThreadingHTTPServer) | integration | PASS |
| 6 | Malformed password/unlock payloads → 400; armed rotation without current → 401; nothing armed by bad payloads | `tests/test_credential_flow.py::test_lock_routes_reject_bad_payloads` | integration | PASS |
| 7 | Full suite regression | `python tests/run_tests.py` → 43/43 | suite | PASS |
| 8 | Live app behavior: setup, verification, shake feedback, Esc/no-bypass, persistence across reload, visual style intact | Bundled-Chromium CDP E2E on port 8755 (see #5/#6 above) | E2E (CDP) | PASS |

## Coverage and known gaps

- No coverage tool configured in this repo (zero-dep suite); the credential module's
  public surface is exercised by two unit tests + two integration tests + the CDP E2E.
- Intentional gaps / follow-up candidates (out of this card's scope):
  - No brute-force rate limiting on `/api/system/unlock` (macOS behaves the same; a
    lockout policy would be a separate hardening card).
  - No "change password" UI in System Settings — the API supports rotation
    (`current_password` + `password`); wiring a Settings pane is a follow-up card.
  - The lock overlay is a browser-preview surface: client-side JS can always be
    inspected; the security boundary is the backend credential, as in the prior cards.
  - Standalone `file://` mode: with no reachable backend the probe fails and the UI
    offers first-run setup (unarmed); arming always requires the backend (fail-safe).