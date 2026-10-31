"""Tests for the Menu Bar & Control Center system preference controls.

Covers the pure validation model (`core/system_prefs.py`) and the live backend
routes (`/api/system/night-shift`, `/api/system/input-source`,
`/api/system/power-mode`) including persisted state in `settings.json`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "aqua-desktop"))


def _load_server_module():
    """Import scripts/preview-aquaos.py with the config dir pointed at a temp dir."""
    tmp_config_dir = Path(tempfile.mkdtemp(prefix="aquaos_prefs_"))
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
    return sys.modules["preview_aquaos_server"], tmp_config_dir


def _post(base: str, path: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_prefs_defaults_and_validation() -> None:
    """Input-source / power-mode accept their canonical + case-insensitive forms."""
    from core.system_prefs import (
        INPUT_SOURCES,
        POWER_MODES,
        PREF_SECTION_DEFAULTS,
        normalize_input_source,
        normalize_night_shift,
        normalize_power_mode,
    )

    assert tuple(INPUT_SOURCES) == ("US", "International", "Dvorak")
    assert tuple(POWER_MODES) == ("Automatic", "Low Power Mode", "High Power Mode")
    assert PREF_SECTION_DEFAULTS == {
        "display": {"night_shift": False},
        "keyboard": {"input_source": "US"},
        "battery": {"power_mode": "Automatic"},
    }

    assert normalize_input_source("US") == "US"
    assert normalize_input_source("dvorak") == "Dvorak"
    assert normalize_input_source("  International ") == "International"
    for bad in (None, 42, "", "Fakeboard"):
        try:
            normalize_input_source(bad)
            raise AssertionError(f"normalize_input_source accepted {bad!r}")
        except ValueError:
            pass

    assert normalize_power_mode("Automatic") == "Automatic"
    assert normalize_power_mode("low power mode") == "Low Power Mode"
    for bad in (None, 7, "", "Turbo"):
        try:
            normalize_power_mode(bad)
            raise AssertionError(f"normalize_power_mode accepted {bad!r}")
        except ValueError:
            pass

    assert normalize_night_shift(True) is True
    assert normalize_night_shift(False) is False
    for bad in (0, "true", None):
        try:
            normalize_night_shift(bad)
            raise AssertionError(f"normalize_night_shift accepted {bad!r}")
        except ValueError:
            pass


def test_config_defaults_match_prefs_model() -> None:
    """AquaConfig ships the same persisted-pref defaults as the validation model."""
    from core.config import AquaConfig
    from core.system_prefs import PREF_SECTION_DEFAULTS

    tmp_dir = Path(tempfile.mkdtemp(prefix="aquaos_prefs_"))
    try:
        cfg = AquaConfig(config_path=tmp_dir / "settings.json")
        for section, defaults in PREF_SECTION_DEFAULTS.items():
            for key, value in defaults.items():
                assert cfg.get(section, key) == value, f"{section}.{key} default mismatch"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_system_prefs_routes_persist() -> None:
    """Live server: the three control endpoints validate, persist, and read back."""
    server_module, tmp_config_dir = _load_server_module()
    server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.AquaDesktopAPIHandler)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 1. Night Shift round-trips and persists
        status, payload = _post(base, "/api/system/night-shift", {"enabled": True})
        assert status == 200 and payload["enabled"] is True, payload
        with urllib.request.urlopen(base + "/api/settings/get", timeout=5) as resp:
            view = json.loads(resp.read().decode("utf-8"))
        assert view["display"]["night_shift"] is True

        settings = json.loads((tmp_config_dir / "settings.json").read_text(encoding="utf-8"))
        assert settings["display"]["night_shift"] is True

        # 2. Input source: canonicalized + invalid input rejected with 400
        status, payload = _post(base, "/api/system/input-source", {"source": "dvorak"})
        assert status == 200 and payload["source"] == "Dvorak", payload
        status, _payload = _post(base, "/api/system/input-source", {"source": "Fakeboard"})
        assert status == 400 and "error" in _payload

        # 3. Power mode: canonicalized + invalid input rejected with 400
        status, payload = _post(base, "/api/system/power-mode", {"mode": "Low Power Mode"})
        assert status == 200 and payload["mode"] == "Low Power Mode", payload
        status, _payload = _post(base, "/api/system/power-mode", {"mode": "Turbo"})
        assert status == 400 and "error" in _payload

        # 4. Persisted state survives on disk after every write
        settings = json.loads((tmp_config_dir / "settings.json").read_text(encoding="utf-8"))
        assert settings["display"]["night_shift"] is True
        assert settings["keyboard"]["input_source"] == "Dvorak"
        assert settings["battery"]["power_mode"] == "Low Power Mode"

        # 5. Regression: the generic settings/update path still persists
        status, payload = _post(
            base, "/api/settings/update", {"section": "appearance", "key": "theme", "value": "light"}
        )
        assert status == 200 and payload.get("saved") is True
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmp_config_dir, ignore_errors=True)