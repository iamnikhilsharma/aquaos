"""
Tests for the lock-screen credential flow (task t_6d5bdf67).

Covers three surfaces:

1. `desktop.html` source contract — the demo password `aquaos` must never
   appear as a plaintext value, the lock input must not be prefilled, and the
   real first-run setup + verify flow must be wired.
2. The pure credential model (`core/credential_store.py`) — PBKDF2-HMAC-SHA256
   hashing, salted per-set, malformed credentials rejected safely (never crash,
   never match).
3. The live backend routes (`/api/system/lock`, `/api/system/password`,
   `/api/system/unlock`) — first-run setup, wrong-password rejection, rotation
   requiring the current password, hash-only persistence on disk, and no hash
   exposure through API responses.

The lock screen previously shipped a hardcoded demo password (`value=\"aquaos\"`
on the input) and an `unlockScreen()` that hid the overlay without verifying
anything — including a global keydown handler that unlocked on ANY key press.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
HTML_PATH = PROJECT_ROOT / "aqua-desktop" / "ui" / "desktop.html"
sys.path.insert(0, str(PROJECT_ROOT / "aqua-desktop"))


# ---------------------------------------------------------------------------
# Source-contract tests (aqua-desktop/ui/desktop.html)
# ---------------------------------------------------------------------------

def test_lock_screen_has_no_plaintext_demo_password() -> None:
    """The demo password is gone from the UI source and the lock inputs are never prefilled."""
    content = HTML_PATH.read_text(encoding="utf-8")

    # 1. The exact demo credential is gone — as an input value or anywhere else as value
    assert 'value="aquaos"' not in content, "demo password still hardcoded in desktop.html"
    assert "value='aquaos'" not in content, "demo password still hardcoded in desktop.html"

    # 2. No password-type input carries a prefilled value attribute (kill it at the root:
    #    any future re-prefill on a password field trips this)
    password_tags = re.findall(r"<input[^>]*type=[\"']password[\"'][^>]*>", content)
    assert password_tags, "lock-screen password input disappeared from desktop.html"
    for tag in password_tags:
        assert "value=" not in tag, f"password input prefilled: {tag}"

    # 3. The old unconditional unlock function is fully replaced
    assert "unlockScreen" not in content, "unconditional unlockScreen() still present"

    # 4. The global keydown handler must not unlock the session on arbitrary keys:
    #    the old snippet `display === 'flex') { unlockScreen();` is a one-keypress bypass
    assert "unlockScreen();" not in content
    assert "lockOverlayVisible()" in content, "lock overlay guard helper missing"


def test_lock_screen_first_run_and_verify_flow_is_wired() -> None:
    """The lock screen offers a first-run password setup mode and a password-verified unlock mode."""
    content = HTML_PATH.read_text(encoding="utf-8")

    # 1. Setup-mode markup: two password fields + shared status line
    assert 'id="lock-setup-input"' in content
    assert 'id="lock-setup-confirm-input"' in content
    assert 'id="lock-status-line"' in content
    assert "placeholder=\"Enter Password\"" in content, "verify-mode placeholder removed"

    # 2. New flow functions replace unlockScreen
    for fn in ("prepareLockScreen", "setLockMode", "submitLockSetup", "attemptUnlock", "cancelLockOrSetup", "showLockError"):
        assert f"function {fn}" in content, f"missing lock-flow function {fn}"

    # 3. Enter/arrow/cancel go through the real flow, not an unconditional hide
    assert "onkeydown=\"if(event.key==='Enter') attemptUnlock()\"" in content

    # 4. The auth calls use raw fetch with the real endpoints (not apiFetch's silent
    #    localOSDispatch fallback, which could fake an unlock when the backend is down)
    assert "'/api/system/lock'" in content
    assert "'/api/system/password'" in content
    assert "'/api/system/unlock'" in content

    # 5. Wrong-password feedback: shake animation + status line error surfaced
    assert "@keyframes aqua-lock-shake" in content
    assert "aqua-lock-shake" in content


# ---------------------------------------------------------------------------
# Pure credential model (core/credential_store.py)
# ---------------------------------------------------------------------------

def test_credential_hash_round_trip_and_salt_uniqueness() -> None:
    """PBKDF2 credential verifies the right password, rejects wrong ones, and salts per set."""
    from core.credential_store import credential_matches, hash_password

    password = "correct horse battery staple 42"
    cred = hash_password(password, iterations=1000)

    assert set(cred) == {"algorithm", "iterations", "salt_hex", "hash_hex"}
    assert cred["algorithm"] == "pbkdf2_sha256"
    assert cred["iterations"] == 1000

    salt = bytes.fromhex(cred["salt_hex"])
    assert len(salt) == 16 and salt.hex() == cred["salt_hex"]
    assert bytes.fromhex(cred["hash_hex"])

    assert credential_matches(password, cred) is True
    assert credential_matches("correct horse battery staple 421", cred) is False
    assert credential_matches("", cred) is False

    # Two hashes of the same password never share a salt or hash
    cred2 = hash_password(password, iterations=1000)
    assert cred2["salt_hex"] != cred["salt_hex"]
    assert cred2["hash_hex"] != cred["hash_hex"]
    assert credential_matches(password, cred2) is True

    # Persisted credential text never contains the plaintext
    dumped = json.dumps(cred)
    assert password not in dumped


def test_password_validation_and_malformed_credentials() -> None:
    """Bad payloads raise ValueError; malformed stored credentials never match."""
    from core.credential_store import credential_matches, hash_password, validate_password

    # Accepted forms return the password unchanged (no stripping — exact credential)
    for good in ("aquaos-pass-01", "passphrase with spaces", "x" * 6, "y" * 72):
        assert validate_password(good) == good

    # Rejected forms
    bad_payloads: list[Any] = [
        None, 42, 3.5, ["pw"], {1: "a"},
        "", "abc", "x" * 5, "z" * 73,
    ]
    for payload in bad_payloads:
        try:
            validate_password(payload)
            raise AssertionError(f"validate_password accepted {payload!r}")
        except ValueError:
            pass

    # Custom field name is surfaced in the error message
    try:
        validate_password("abc", field="current_password")
        raise AssertionError("validate_password accepted a short current_password")
    except ValueError as exc:
        assert "current_password" in str(exc)

    # Malformed / unknown-algorithm stored credentials never match (and never crash)
    real = hash_password("valid-password-1", iterations=1000)
    malformed = [
        None, {}, [], "string", 42,
        {}, {**real, "algorithm": "md5"}, {**real, "algorithm": "pbkdf2_sha256", "iterations": -1},
        {k: v for k, v in real.items() if k != "hash_hex"},
        {k: v for k, v in real.items() if k != "salt_hex"},
        {**real, "salt_hex": "not-hex!!"},
        {**real, "iterations": "fast"},
    ]
    for credential in malformed:
        assert credential_matches("valid-password-1", credential) is False, f"matched malformed credential {credential!r}"


# ---------------------------------------------------------------------------
# Live server routes
# ---------------------------------------------------------------------------

def _load_server_module() -> Tuple[Any, Path]:
    """Import scripts/preview-aquaos.py with config + credential store in a temp dir.

    Mirrors tests/test_system_prefs.py: the first import in the process populates
    sys.modules; later calls re-point the module globals at a fresh temp dir so
    each test observes its own settings.json and credentials.json.
    """
    tmp_config_dir = Path(tempfile.mkdtemp(prefix="aquaos_cred_"))
    os.environ["AQUAOS_CONFIG_DIR"] = str(tmp_config_dir)
    if "preview_aquaos_server" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "preview_aquaos_server", PROJECT_ROOT / "scripts" / "preview-aquaos.py"
        )
        assert spec is not None, "preview-aquaos.py spec missing"
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None, "preview-aquaos.py spec loader missing"
        sys.modules["preview_aquaos_server"] = module
        spec.loader.exec_module(module)
    module = sys.modules["preview_aquaos_server"]
    from core.config import AquaConfig
    from core.credential_store import CredentialStore

    module.config = AquaConfig(config_path=tmp_config_dir / "settings.json")
    module.credential_store = CredentialStore(store_path=tmp_config_dir / "credentials.json")
    module.hydrate_runtime_state()
    return module, tmp_config_dir


def _request(base: str, path: str, payload: Any = None) -> Tuple[int, Dict[str, Any]]:
    """GET (or POST when a payload is given — including intentionally malformed bodies)."""
    method = "POST" if payload is not None else "GET"
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@contextmanager
def _live_server():
    module, tmp_config_dir = _load_server_module()
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.AquaDesktopAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_config_dir
    finally:
        server.shutdown()
        server.server_close()


def test_lock_routes_setup_verify_rotation_and_persist() -> None:
    """First-run setup, wrong-password rejection, current-password-gated rotation, hash-only persistence."""
    from core.credential_store import credential_matches

    password = "aqua-test-pw-9"
    rotated = "rotated-pw-77"

    with _live_server() as (base, tmp_config_dir):
        # 1. Fresh install: no credential armed, and the status endpoint exposes nothing else
        status, payload = _request(base, "/api/system/lock")
        assert status == 200 and payload == {"has_password": False}, payload

        # 2. First-run setup persists a salted PBKDF2 credential — never the plaintext
        status, payload = _request(base, "/api/system/password", {"password": password})
        assert status == 200 and payload == {"has_password": True}, payload

        cred_path = tmp_config_dir / "credentials.json"
        assert cred_path.exists(), "credential file not persisted"
        disk_text = cred_path.read_text(encoding="utf-8")
        assert password not in disk_text and rotated not in disk_text, "plaintext password persisted to disk"
        disk_cred = json.loads(disk_text)
        assert set(disk_cred) == {"algorithm", "iterations", "salt_hex", "hash_hex"}
        assert disk_cred["algorithm"] == "pbkdf2_sha256"
        assert disk_cred["iterations"] >= 60000
        assert credential_matches(password, disk_cred) is True
        assert credential_matches("wrong", disk_cred) is False

        # 3. Status exposes only the boolean — never hash material
        status, payload = _request(base, "/api/system/lock")
        assert status == 200 and payload == {"has_password": True}, payload
        assert "hash_hex" not in json.dumps(payload) and "salt_hex" not in json.dumps(payload)

        # 4. Unlock verification: wrong password rejected, right password accepted
        status, payload = _request(base, "/api/system/unlock", {"password": "wrong-guess"})
        assert status == 401 and payload["unlocked"] is False and "error" in payload, payload
        status, payload = _request(base, "/api/system/unlock", {"password": password})
        assert status == 200 and payload == {"unlocked": True, "has_password": True}, payload

        # 5. Rotation requires the current password (missing -> 401, wrong -> 401)
        status, payload = _request(base, "/api/system/password", {"password": rotated})
        assert status == 401 and "error" in payload, payload
        status, payload = _request(base, "/api/system/password", {"current_password": "nope", "password": rotated})
        assert status == 401 and "error" in payload, payload

        # 6. Correct current password rotates; the old credential stops verifying
        status, payload = _request(base, "/api/system/password", {"current_password": password, "password": rotated})
        assert status == 200 and payload == {"has_password": True}, payload
        status, payload = _request(base, "/api/system/unlock", {"password": password})
        assert status == 401, payload
        status, payload = _request(base, "/api/system/unlock", {"password": rotated})
        assert status == 200 and payload == {"unlocked": True, "has_password": True}, payload

        # 7. Rotation rewrote disk (new hash, still no plaintext)
        disk_cred2 = json.loads(cred_path.read_text(encoding="utf-8"))
        assert disk_cred2["hash_hex"] != disk_cred["hash_hex"]
        assert password not in json.dumps(disk_cred2)


def test_lock_routes_reject_bad_payloads() -> None:
    """Malformed password/unlock payloads get 400s (or current-required 401) and arm nothing."""
    with _live_server() as (base, tmp_config_dir):
        for bad_body in ({}, {"password": None}, {"password": 42}, {"password": "abc"}, {"password": "x" * 73}, ["pw"]):
            status, payload = _request(base, "/api/system/password", bad_body)
            assert status == 400 and "error" in payload, (bad_body, payload)

        for bad_body in ({}, {"password": None}, {"password": 7}, ["pw"]):
            status, payload = _request(base, "/api/system/unlock", bad_body)
            assert status == 400 and "error" in payload, (bad_body, payload)

        # Nothing above armed a credential
        status, payload = _request(base, "/api/system/lock")
        assert status == 200 and payload == {"has_password": False}, payload

        # Once armed, a rotation missing current_password is 401 (current required)
        status, _payload = _request(base, "/api/system/password", {"password": "some real pw 1"})
        assert status == 200
        status, payload = _request(base, "/api/system/password", {"password": "another real pw"})
        assert status == 401 and "error" in payload, payload