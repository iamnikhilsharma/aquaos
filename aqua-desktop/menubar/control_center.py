"""AquaOS Control Center (control_center.py).

macOS Sonoma/Sequoia-inspired frosted glass Control Center popover with quick toggles for:
- Wi-Fi, Bluetooth, AirDrop (LocalSend)
- Dark Mode & Do Not Disturb
- Neural Boost AI Performance Mode (Flash Attention + RAM Reclaim)
- Display Brightness & Sound Volume Sliders
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ai.neural_boost import NeuralBoostManager
from core.config import AquaConfig
from core.system_services import SystemServices


@dataclass
class ControlCenterState:
    """Snapshot of all quick-toggle states and sliders in the Control Center."""

    wifi_enabled: bool
    wifi_ssid: str
    bluetooth_enabled: bool
    dark_mode: bool
    neural_boost: bool
    gpu_backend: str
    firewall_enabled: bool
    brightness: int
    volume: int
    battery_percent: int
    battery_charging: bool


class ControlCenterController:
    """Manages state and actions for the macOS-style Control Center popover."""

    def __init__(self, config: AquaConfig, services: SystemServices, neural_boost: NeuralBoostManager) -> None:
        self.config = config
        self.services = services
        self.neural_boost = neural_boost
        self._wifi_enabled = True
        self._bluetooth_enabled = True

    def get_state(self) -> ControlCenterState:
        bat = self.services.get_battery_status()
        nb = self.neural_boost.status()
        return ControlCenterState(
            wifi_enabled=self._wifi_enabled,
            wifi_ssid="AquaNet-5G" if self._wifi_enabled else "Off",
            bluetooth_enabled=self._bluetooth_enabled,
            dark_mode=(self.config.get("appearance", "theme", "dark") == "dark"),
            neural_boost=nb.enabled,
            gpu_backend=nb.gpu_backend,
            firewall_enabled=bool(self.config.get("security", "firewall_enabled", True)),
            brightness=self.services.get_brightness(),
            volume=self.services.get_volume(),
            battery_percent=bat["percentage"],
            battery_charging=bat["charging"],
        )

    def toggle_dark_mode(self) -> bool:
        current = self.config.get("appearance", "theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        self.config.set("appearance", "theme", new_theme)
        return new_theme == "dark"

    def toggle_neural_boost(self) -> Dict[str, Any]:
        nb = self.neural_boost.status()
        updated = self.neural_boost.set_neural_boost(not nb.enabled)
        self.config.set("ai", "neural_boost_enabled", updated.enabled)
        return {
            "enabled": updated.enabled,
            "gpu_backend": updated.gpu_backend,
            "reclaimed_mb": updated.reclaimed_mb,
        }

    def toggle_wifi(self) -> bool:
        self._wifi_enabled = not self._wifi_enabled
        return self._wifi_enabled

    def toggle_bluetooth(self) -> bool:
        self._bluetooth_enabled = not self._bluetooth_enabled
        return self._bluetooth_enabled

    def set_volume(self, value: int) -> int:
        return self.services.set_volume(value)

    def set_brightness(self, value: int) -> int:
        return self.services.set_brightness(value)
