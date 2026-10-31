"""Pure validation model for Menu Bar & Control Center system preference controls.

Single source of truth for the canonical values and defaults shared by the
backend routes (`scripts/preview-aquaos.py`) and the persisted defaults in
`core/config.py`.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

INPUT_SOURCES: Tuple[str, ...] = ("US", "International", "Dvorak")
POWER_MODES: Tuple[str, ...] = ("Automatic", "Low Power Mode", "High Power Mode")

# Sections contributed to AquaConfig's DEFAULT_CONFIG (persisted in settings.json).
PREF_SECTION_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "display": {"night_shift": False},
    "keyboard": {"input_source": "US"},
    "battery": {"power_mode": "Automatic"},
}


def _canonical(name: Any, canonical_values: Tuple[str, ...], label: str) -> str:
    """Return the canonical spelling for a case-insensitive match, else raise."""
    if isinstance(name, str):
        folded = name.strip().casefold()
        for candidate in canonical_values:
            if candidate.casefold() == folded:
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
    if isinstance(value, bool):
        return value
    raise ValueError(f"Night Shift preference must be a boolean, got: {value!r}")