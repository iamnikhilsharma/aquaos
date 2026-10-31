"""AquaOS Configuration Manager.

Manages user preferences stored in ~/.config/aquaos/settings.json with schema defaults,
atomic writes, and change listener callbacks for live reload across the desktop shell.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.system_prefs import PREF_SECTION_DEFAULTS


DEFAULT_CONFIG: Dict[str, Any] = {
    "appearance": {
        "theme": "dark",  # "dark" | "light" | "auto"
        "accent_color": "#0A84FF",  # macOS system blue
        "accent_name": "Blue",
        "frosted_glass": True,
        "blur_radius": 24,
        "corner_radius": 12,
        "wallpaper": "/opt/aquaos/theme/wallpaper.svg",
        "font_family": "Inter, SF Pro Display, sans-serif",
    },
    "dock": {
        "icon_size": 52,
        "magnification_enabled": True,
        "magnification_scale": 1.65,
        "magnification_radius": 150.0,
        "auto_hide": False,
        "position": "bottom",  # "bottom" | "left" | "right"
        "show_running_indicators": True,
        "pinned_apps": [
            "org.aquaos.Finder",
            "org.mozilla.Firefox",
            "org.mozilla.Thunderbird",
            "org.aquaos.SnapStore",
            "org.aquaos.Music",
            "org.aquaos.QuickTime",
            "org.aquaos.Preview",
            "org.aquaos.Terminal",
            "org.aquaos.AIStudio",
            "org.aquaos.ShieldCenter",
            "org.aquaos.SystemSettings",
        ],
    },
    "default_apps": {
        "browser": "firefox",
        "web_browser": "firefox",
        "email": "thunderbird",
        "image_viewer": "preview",
        "music_player": "music",
        "video_player": "quicktime",
        "package_manager": "snap-store",
        "app_store": "snap-store",
        "terminal": "terminal",
        "file_manager": "finder",
    },
    "menubar": {
        "height": 28,
        "show_battery_percentage": True,
        "use_24h_clock": False,
        "show_seconds": False,
        "show_ai_orb": True,
        "show_shield_badge": True,
    },
    "security": {
        "mode": "gatekeeper",  # "strict" | "gatekeeper" | "developer"
        "enforce_sandbox_foreign_binaries": True,
        "sandbox_allow_network_by_default": False,
        "immutable_rootfs_check": True,
        "firewall_enabled": True,
        "quarantine_downloads": True,
        "tcc_permissions": {
            # app_id -> {"documents": bool, "downloads": bool, "network": bool, "camera": bool}
        },
    },
    "ai": {
        "provider": "ollama",  # "ollama" | "llamacpp" | "openai_compatible"
        "endpoint": "http://127.0.0.1:11434",
        "llamacpp_endpoint": "http://127.0.0.1:8080",
        "default_model": "deepseek-r1:7b",
        "coding_model": "qwen2.5-coder:7b",
        "vision_model": "llava:7b",
        "neural_boost_enabled": True,
        "flash_attention": True,
        "kv_cache_quantization": "q8_0",  # "f16" | "q8_0" | "q4_0"
        "sandbox_code_execution": True,
        "gpu_backend": "auto",  # "auto" | "cuda" | "rocm" | "vulkan" | "cpu"
        "context_length": 8192,
    },
}

# Menu Bar & Control Center persisted prefs (display/keyboard/battery) share
# one source of truth in core.system_prefs so the UI, routes, and defaults agree.
DEFAULT_CONFIG.update(PREF_SECTION_DEFAULTS)


class AquaConfig:
    """Manages reading, writing, and observing AquaOS settings."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        if config_path is None:
            config_dir = Path(os.environ.get("AQUAOS_CONFIG_DIR", Path.home() / ".config" / "aquaos"))
            self.config_path = config_dir / "settings.json"
        else:
            self.config_path = Path(config_path)

        self._data: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load settings from disk, merging with DEFAULT_CONFIG."""
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._deep_merge(self._data, raw)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            self.save()
        return self._data

    def save(self) -> None:
        """Persist current configuration atomically to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.config_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp_path.replace(self.config_path)
        except OSError:
            pass
        for callback in list(self._listeners):
            try:
                callback(self._data)
            except Exception:
                pass

    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """Retrieve a configuration section or a specific key within a section."""
        sec = self._data.get(section)
        if key is None:
            return sec if sec is not None else default
        if isinstance(sec, dict):
            return sec.get(key, default)
        return default

    def set(self, section: str, key: str, value: Any, auto_save: bool = True) -> None:
        """Update a configuration key and optionally save to disk."""
        if section not in self._data or not isinstance(self._data[section], dict):
            self._data[section] = {}
        self._data[section][key] = value
        if auto_save:
            self.save()

    def reset_to_defaults(self) -> None:
        """Reset all configuration values to factory defaults."""
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self.save()

    def on_change(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a listener invoked whenever settings are saved."""
        self._listeners.append(callback)

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def as_dict(self) -> Dict[str, Any]:
        """Return a copy of the configuration dictionary."""
        return copy.deepcopy(self._data)

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                AquaConfig._deep_merge(base[k], v)
            else:
                base[k] = v
