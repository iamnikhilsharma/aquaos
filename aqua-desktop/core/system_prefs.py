"""Pure validation model for persisted system preference controls.

Single source of truth for the canonical values and defaults shared by the
backend routes (`scripts/preview-aquaos.py`) and the persisted defaults in
`core/config.py`.

Covers the Menu Bar & Control Center controls (Night Shift / input source /
power mode) and the System Settings preference panes (connectivity,
notifications, focus, sharing, firewall).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

INPUT_SOURCES: Tuple[str, ...] = ("US", "International", "Dvorak")
POWER_MODES: Tuple[str, ...] = ("Automatic", "Low Power Mode", "High Power Mode")

# Runtime toggle features shared by the menu bar / Control Center and the
# System Settings connectivity / focus panes. Each maps to a persisted
# (section, key) pair below.
TOGGLE_FEATURES: Tuple[str, ...] = ("wifi", "bluetooth", "dnd")
TOGGLE_PERSIST_KEYS: Dict[str, Tuple[str, str]] = {
    "wifi": ("network", "wifi_enabled"),
    "bluetooth": ("network", "bluetooth_enabled"),
    "dnd": ("focus", "dnd_enabled"),
}

NOTIFICATION_BOOL_KEYS: Tuple[str, ...] = (
    "allow_when_sleeping",
    "allow_when_mirroring",
    "badge_app_icon",
    "play_alert_sound",
)
NOTIFICATION_GROUPINGS: Tuple[str, ...] = ("automatic", "by_app", "off")

FOCUS_MODES: Tuple[str, ...] = ("Do Not Disturb", "Personal", "Work", "Sleep")
AIRDROP_VISIBILITIES: Tuple[str, ...] = ("off", "contacts", "everyone")
SHARING_SERVICES: Tuple[str, ...] = (
    "screen_sharing",
    "file_sharing",
    "remote_login",
    "internet_sharing",
)
FIREWALL_BOOL_KEYS: Tuple[str, ...] = ("firewall_enabled", "stealth_mode")

# Sections contributed to AquaConfig's DEFAULT_CONFIG (persisted in settings.json).
PREF_SECTION_DEFAULTS: Dict[str, Dict[str, Any]] = {
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
    # 'security' already exists in DEFAULT_CONFIG; these defaults merge into it.
    "security": {"firewall_enabled": True, "stealth_mode": False},
}


def _canonical(name: Any, canonical_values: Tuple[str, ...], label: str) -> str:
    """Return the canonical spelling for a case-insensitive match, else raise.

    Matching ignores separator style too, so macOS spellings like 'By App',
    'Wi-Fi', or 'Remote Login' canonicalize to 'by_app', 'wifi', 'remote_login'.
    """
    if isinstance(name, str):
        folded = name.strip().casefold()
        for candidate in canonical_values:
            if candidate.casefold() == folded:
                return candidate
        collapsed = folded.replace("-", "").replace("_", "").replace(" ", "")
        for candidate in canonical_values:
            if candidate.casefold().replace("-", "").replace("_", "").replace(" ", "") == collapsed:
                return candidate
    raise ValueError(
        f"Unknown {label}: {name!r}. Expected one of: {', '.join(canonical_values)}"
    )


def normalize_input_source(value: Any) -> str:
    """Validate an input source name ('US', 'International', or 'Dvorak')."""
    return _canonical(value, INPUT_SOURCES, "input source")


def normalize_power_mode(value: Any) -> str:
    """Validate a power mode name ('Automatic', 'Low Power Mode', 'High Power Mode')."""
    return _canonical(value, POWER_MODES, "power mode")


def normalize_night_shift(value: Any) -> bool:
    """Validate the Night Shift on/off flag (strict boolean)."""
    return normalize_bool(value, "Night Shift preference")


def normalize_bool(value: Any, label: str) -> bool:
    """Validate a strict boolean preference flag."""
    if isinstance(value, bool):
        return value
    raise ValueError(f"{label} must be a boolean, got: {value!r}")


def normalize_toggle_feature(value: Any) -> str:
    """Validate a runtime toggle feature; accepts 'wifi'/'Wi-Fi', 'DND', 'Bluetooth'."""
    return _canonical(value, TOGGLE_FEATURES, "toggle feature")


def normalize_notification_grouping(value: Any) -> str:
    """Validate a notification grouping mode ('automatic', 'by_app', 'off')."""
    return _canonical(value, NOTIFICATION_GROUPINGS, "notification grouping")


def normalize_focus_mode(value: Any) -> str:
    """Validate a Focus profile ('Do Not Disturb', 'Personal', 'Work', 'Sleep')."""
    return _canonical(value, FOCUS_MODES, "focus mode")


def normalize_airdrop_visibility(value: Any) -> str:
    """Validate an AirDrop visibility ('off', 'contacts', or 'everyone')."""
    return _canonical(value, AIRDROP_VISIBILITIES, "AirDrop visibility")


def normalize_sharing_service(value: Any) -> str:
    """Validate a sharing service ('remote_login' etc)."""
    return _canonical(value, SHARING_SERVICES, "sharing service")


def normalize_firewall_prefs(body: Dict[str, Any]) -> Dict[str, bool]:
    """Validate firewall preference updates ('firewall_enabled', 'stealth_mode')."""
    return normalize_toggle_payload(body, FIREWALL_BOOL_KEYS, "firewall preference")


def normalize_toggle_payload(
    body: Dict[str, Any], bool_keys: Iterable[str], label: str
) -> Dict[str, bool]:
    """Validate an update payload of strict-boolean preference keys.

    Returns only the provided keys (already normalized). Unknown keys or
    non-boolean values raise ValueError so routes can answer with a 400.
    """
    if not isinstance(body, dict):
        raise ValueError(f"{label} update must be a JSON object, got: {body!r}")
    normalized: Dict[str, bool] = {}
    allowed = set(bool_keys)
    for key, value in body.items():
        if key not in allowed:
            raise ValueError(
                f"Unknown {label} setting: {key!r}. Expected one of: "
                f"{', '.join(sorted(bool_keys))}"
            )
        normalized[key] = normalize_bool(value, f"{label}.{key}")
    return normalized