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
    """Input-source / power-mode / connectivity / notification / focus / sharing / firewall
    prefs accept their canonical + case-insensitive forms (strict elsewhere)."""
    from core.system_prefs import (
        AIRDROP_VISIBILITIES,
        FOCUS_MODES,
        INPUT_SOURCES,
        NOTIFICATION_GROUPINGS,
        POWER_MODES,
        PREF_SECTION_DEFAULTS,
        SHARING_SERVICES,
        TOGGLE_FEATURES,
        normalize_airdrop_visibility,
        normalize_bool,
        normalize_firewall_prefs,
        normalize_focus_mode,
        normalize_input_source,
        normalize_night_shift,
        normalize_notification_grouping,
        normalize_power_mode,
        normalize_sharing_service,
        normalize_toggle_feature,
    )

    assert tuple(INPUT_SOURCES) == ("US", "International", "Dvorak")
    assert tuple(POWER_MODES) == ("Automatic", "Low Power Mode", "High Power Mode")
    assert PREF_SECTION_DEFAULTS == {
        "display": {"night_shift": False},
        "keyboard": {"input_source": "US"},
        "battery": {"power_mode": "Automatic"},
        "network": {
            "wifi_enabled": True,
            "bluetooth_enabled": True,
            "private_mac_randomization": True,
        },
        "notifications": {
            "allow_when_sleeping": False,
            "allow_when_mirroring": False,
            "badge_app_icon": True,
            "play_alert_sound": True,
            "grouping": "automatic",
        },
        "focus": {"mode": "Do Not Disturb", "dnd_enabled": False},
        "sharing": {
            "airdrop_visibility": "contacts",
            "screen_sharing": False,
            "file_sharing": False,
            "remote_login": False,
            "internet_sharing": False,
        },
        "security": {"firewall_enabled": True, "stealth_mode": False},
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

    # Connectivity / Focus runtime toggles shared by the menu bar and System Settings
    assert tuple(TOGGLE_FEATURES) == ("wifi", "bluetooth", "dnd")
    assert normalize_toggle_feature("Wi-Fi") == "wifi"
    assert normalize_toggle_feature("DND") == "dnd"
    for bad in (None, 3, "", "hotspot"):
        try:
            normalize_toggle_feature(bad)
            raise AssertionError(f"normalize_toggle_feature accepted {bad!r}")
        except ValueError:
            pass
    assert normalize_bool(True, "feature") is True
    assert normalize_bool(False, "feature") is False
    for bad_bad in (1, "true", None):
        try:
            normalize_bool(bad_bad, "feature")
            raise AssertionError(f"normalize_bool accepted {bad_bad!r}")
        except ValueError:
            pass

    # Notification prefs
    assert tuple(NOTIFICATION_GROUPINGS) == ("automatic", "by_app", "off")
    assert normalize_notification_grouping("By App") == "by_app"
    for bad in (None, 0, "", "stacked"):
        try:
            normalize_notification_grouping(bad)
            raise AssertionError(f"normalize_notification_grouping accepted {bad!r}")
        except ValueError:
            pass

    # Focus profiles
    assert tuple(FOCUS_MODES) == ("Do Not Disturb", "Personal", "Work", "Sleep")
    assert normalize_focus_mode("work") == "Work"
    for bad in (None, 5, "", "Party"):
        try:
            normalize_focus_mode(bad)
            raise AssertionError(f"normalize_focus_mode accepted {bad!r}")
        except ValueError:
            pass

    # AirDrop & Handoff visibility
    assert tuple(AIRDROP_VISIBILITIES) == ("off", "contacts", "everyone")
    assert normalize_airdrop_visibility("Everyone") == "everyone"
    for bad in (None, 1, "", "radius"):
        try:
            normalize_airdrop_visibility(bad)
            raise AssertionError(f"normalize_airdrop_visibility accepted {bad!r}")
        except ValueError:
            pass

    # Shared services (Screen Sharing, File Sharing, Remote Login, Internet Sharing)
    assert tuple(SHARING_SERVICES) == (
        "screen_sharing",
        "file_sharing",
        "remote_login",
        "internet_sharing",
    )
    assert normalize_sharing_service("Remote Login") == "remote_login"
    for bad in (None, 9, "", "vnc"):
        try:
            normalize_sharing_service(bad)
            raise AssertionError(f"normalize_sharing_service accepted {bad!r}")
        except ValueError:
            pass

    # Firewall prefs (application firewall + stealth mode)
    assert normalize_firewall_prefs({"firewall_enabled": False, "stealth_mode": True}) == {
        "firewall_enabled": False,
        "stealth_mode": True,
    }
    assert normalize_firewall_prefs({}) == {}
    for bad_payload in ({"stealth": True}, {"firewall_enabled": "yes"}, ["firewall_enabled"]):
        try:
            normalize_firewall_prefs(bad_payload)
            raise AssertionError(f"normalize_firewall_prefs accepted {bad_payload!r}")
        except ValueError:
            pass


def test_config_defaults_match_prefs_model() -> None:
    """AquaConfig ships the same persisted-pref defaults as the validation model,
    and pref-section merges never clobber pre-existing config sections."""
    from core.config import AquaConfig
    from core.system_prefs import PREF_SECTION_DEFAULTS

    tmp_dir = Path(tempfile.mkdtemp(prefix="aquaos_prefs_"))
    try:
        cfg = AquaConfig(config_path=tmp_dir / "settings.json")
        for section, defaults in PREF_SECTION_DEFAULTS.items():
            for key, value in defaults.items():
                assert cfg.get(section, key) == value, f"{section}.{key} default mismatch"
        # Section merge for 'security' must extend, not replace, the shipped section
        assert cfg.get("security", "mode") == "gatekeeper"
        assert cfg.get("security", "tcc_permissions") == {}
        # and every pre-existing section must survive the merge untouched
        assert cfg.get("ai", "provider") == "ollama"
        assert cfg.get("appearance", "theme") == "dark"
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


def _get(base: str, path: str) -> tuple[int, Dict[str, Any]]:
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_settings_tabs_routes_persist() -> None:
    """Live server: connectivity / notification / focus / sharing / firewall routes
    validate, persist to settings.json, reject invalid input with 400, and the
    runtime toggle endpoint now persists instead of mutating memory only."""
    server_module, tmp_config_dir = _load_server_module()
    server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.AquaDesktopAPIHandler)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings_path = tmp_config_dir / "settings.json"

        # 1. /api/system/toggle is persisted now (Wi-Fi / Bluetooth / DND), not memory-only
        status, payload = _post(base, "/api/system/toggle", {"feature": "Wi-Fi", "enabled": False})
        assert status == 200 and payload == {"feature": "wifi", "enabled": False}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["network"]["wifi_enabled"] is False
        status, payload = _post(base, "/api/system/toggle", {"feature": "bluetooth", "enabled": True})
        assert status == 200 and payload == {"feature": "bluetooth", "enabled": True}
        status, payload = _post(base, "/api/system/toggle", {"feature": "dnd", "enabled": True})
        assert status == 200 and payload == {"feature": "dnd", "enabled": True}
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["network"]["bluetooth_enabled"] is True
        assert disk["focus"]["dnd_enabled"] is True
        # The in-memory runtime state is updated too (status route reflects it)
        status, state = _get(base, "/api/system/status")
        assert status == 200
        assert state["wifi"]["enabled"] is False
        assert state["dnd"] is True
        # Invalid input rejected with 400
        for bad_body in ({"feature": "hotspot", "enabled": True}, {"feature": "wifi", "enabled": "yes"}):
            status, payload = _post(base, "/api/system/toggle", bad_body)
            assert status == 400 and "error" in payload, (bad_body, payload)

        # 2. Firewall prefs (Application Firewall + Stealth Mode) persist under security.*
        status, payload = _post(
            base, "/api/system/firewall", {"firewall_enabled": False, "stealth_mode": True}
        )
        assert status == 200 and payload == {"firewall_enabled": False, "stealth_mode": True}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["security"]["firewall_enabled"] is False
        assert disk["security"]["stealth_mode"] is True
        status, _payload = _post(base, "/api/system/firewall", {"stealth": True})
        assert status == 400 and "error" in _payload

        # 3. Private Wi-Fi Address toggle persists under network.*
        status, payload = _post(base, "/api/system/private-mac", {"enabled": False})
        assert status == 200 and payload == {"enabled": False}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["network"]["private_mac_randomization"] is False
        status, _payload = _post(base, "/api/system/private-mac", {"enabled": 1})
        assert status == 400 and "error" in _payload

        # 4. Notification prefs persist under notifications.* and validate per-field
        status, payload = _post(
            base,
            "/api/system/notifications",
            {"grouping": "By App", "badge_app_icon": False, "allow_when_sleeping": True},
        )
        assert status == 200 and payload == {
            "grouping": "by_app",
            "badge_app_icon": False,
            "allow_when_sleeping": True,
        }, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["notifications"]["grouping"] == "by_app"
        assert disk["notifications"]["badge_app_icon"] is False
        assert disk["notifications"]["allow_when_sleeping"] is True
        status, _payload = _post(base, "/api/system/notifications", {"grouping": "stacked"})
        assert status == 400 and "error" in _payload
        status, _payload = _post(base, "/api/system/notifications", {})
        assert status == 400 and "error" in _payload  # nothing to update

        # 5. Focus profile persists (canonical form) under focus.mode
        status, payload = _post(base, "/api/system/focus", {"mode": "work"})
        assert status == 200 and payload == {"mode": "Work"}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["focus"]["mode"] == "Work"
        status, _payload = _post(base, "/api/system/focus", {"mode": "Party"})
        assert status == 400 and "error" in _payload

        # 6. Sharing services persist one by one under sharing.*
        status, payload = _post(base, "/api/system/sharing", {"service": "Remote Login", "enabled": True})
        assert status == 200 and payload == {"service": "remote_login", "enabled": True}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["sharing"]["remote_login"] is True
        status, _payload = _post(base, "/api/system/sharing", {"service": "vnc", "enabled": True})
        assert status == 400 and "error" in _payload
        status, _payload = _post(base, "/api/system/sharing", {"service": "file_sharing", "enabled": "on"})
        assert status == 400 and "error" in _payload

        # 7. AirDrop visibility persists with canonical spelling
        status, payload = _post(base, "/api/system/airdrop", {"visibility": "Everyone"})
        assert status == 200 and payload == {"visibility": "everyone"}, payload
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["sharing"]["airdrop_visibility"] == "everyone"
        status, _payload = _post(base, "/api/system/airdrop", {"visibility": "radius"})
        assert status == 400 and "error" in _payload

        # 8. Persisted connectivity state is hydrated into runtime state at boot:
        #    a fresh AquaConfig-based lookup must agree with what toggle wrote
        from core.config import AquaConfig

        hydrated = AquaConfig(config_path=settings_path)
        assert hydrated.get("network", "wifi_enabled") is False
        assert hydrated.get("focus", "dnd_enabled") is True
    finally:
        server.shutdown()
        server.server_close()


def test_storage_usage_route() -> None:
    """GET /api/storage/usage returns real disk telemetry plus a real, bounded
    per-directory breakdown of the project root for the Storage pane."""
    server_module, _tmp_config_dir = _load_server_module()
    server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.AquaDesktopAPIHandler)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, usage = _get(base, "/api/storage/usage")
        assert status == 200, usage

        assert isinstance(usage["disk_total_gb"], float) and usage["disk_total_gb"] > 0
        assert isinstance(usage["disk_free_gb"], float) and usage["disk_free_gb"] >= 0
        assert 0 <= usage["disk_percent"] <= 100

        categories = usage["categories"]
        assert isinstance(categories, list) and len(categories) >= 1
        for entry in categories:
            assert isinstance(entry["name"], str) and entry["name"]
            assert isinstance(entry["size_bytes"], int) and entry["size_bytes"] >= 0
            assert isinstance(entry["percent"], float) and 0 <= entry["percent"] <= 100
        sizes = [e["size_bytes"] for e in categories]
        assert sizes == sorted(sizes, reverse=True), "categories sorted descending by size"
        names = {e["name"] for e in categories}
        assert "aqua-desktop" in names, "project root breakdown must include aqua-desktop"

        largest = usage["largest_files"]
        assert isinstance(largest, list)
        for entry in largest:
            assert isinstance(entry["size_bytes"], int) and entry["size_bytes"] > 0
            assert isinstance(entry["path"], str) and entry["path"]
        if len(largest) >= 2:
            as_sizes = [e["size_bytes"] for e in largest]
            assert as_sizes == sorted(as_sizes, reverse=True)
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(_tmp_config_dir, ignore_errors=True)