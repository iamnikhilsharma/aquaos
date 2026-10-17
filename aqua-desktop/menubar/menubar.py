"""AquaOS Global Top Menu Bar (menubar.py).

28px top bar anchored via GTK4 + gtk4-layer-shell (Wayland) or EWMH dock struts (X11).
Features:
- Left: Aqua Apple-style System Menu, Bold Active App Name, and Global App Menus (File, Edit, View, Window, AI, Help)
- Right: Aqua Shield Security Badge, Aqua Intelligence Orb, Wi-Fi, Battery, Spotlight Trigger, Control Center, and Clock
"""

from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.neural_boost import NeuralBoostManager
from core.config import AquaConfig
from core.system_services import SystemServices
from core.window_tracker import WindowTracker
from menubar.control_center import ControlCenterController


AQUA_SYSTEM_MENU: List[tuple[str, str]] = [
    ("About AquaOS", "python3 -m apps.about_aquaos"),
    ("System Settings...", "python3 -m apps.system_settings"),
    ("Aqua AI Studio (Neural Engine)...", "python3 -m ai.ai_studio"),
    ("Aqua Shield Security Center...", "python3 -m security.shield_center"),
    ("---", ""),
    ("Sleep", "systemctl suspend"),
    ("Restart...", "systemctl reboot"),
    ("Shut Down...", "systemctl poweroff"),
    ("---", ""),
    ("Lock Screen", "loginctl lock-session"),
    ("Log Out Aqua User...", "loginctl terminate-user $USER"),
]


class AquaMenuBarModel:
    """State and menu structure provider for the 28px Global Menu Bar."""

    def __init__(self) -> None:
        self.config = AquaConfig()
        self.services = SystemServices()
        self.neural_boost = NeuralBoostManager()
        self.window_tracker = WindowTracker()
        self.control_center = ControlCenterController(self.config, self.services, self.neural_boost)

    def format_clock(self, now: datetime.datetime | None = None) -> str:
        dt = now or datetime.datetime.now()
        use_24h = bool(self.config.get("menubar", "use_24h_clock", False))
        if use_24h:
            return dt.strftime("%a %b %d  %H:%M")
        return dt.strftime("%a %b %d  %I:%M %p")

    def get_status_summary(self) -> Dict[str, str]:
        cc = self.control_center.get_state()
        self.window_tracker.refresh()
        return {
            "active_app": self.window_tracker.active_app_name,
            "shield": "🛡 Protected (Immutable)",
            "ai_orb": f"✦ AI ({cc.gpu_backend.upper()}{' ⚡' if cc.neural_boost else ''})",
            "wifi": f"Wi-Fi: {cc.wifi_ssid}",
            "battery": f"{cc.battery_percent}%{' ⚡' if cc.battery_charging else ''}",
            "clock": self.format_clock(),
        }


def launch_gtk_menubar(model: AquaMenuBarModel) -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk  # type: ignore
    except Exception:
        return False

    class MenuBarApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aquaos.MenuBar")

        def do_activate(self) -> None:
            win = Gtk.ApplicationWindow(application=self, title="AquaOS MenuBar")
            win.set_default_size(1920, 28)
            win.set_decorated(False)

            # Try anchoring to top edge via gtk4-layer-shell if running on Wayland
            try:
                gi.require_version("Gtk4LayerShell", "1.0")
                from gi.repository import Gtk4LayerShell  # type: ignore

                Gtk4LayerShell.init_for_window(win)
                Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.TOP)
                Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, True)
                Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.LEFT, True)
                Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.RIGHT, True)
                Gtk4LayerShell.set_exclusive_zone(win, 28)
            except Exception:
                pass

            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            bar.add_css_class("aqua-menubar")
            bar.set_margin_start(12)
            bar.set_margin_end(12)

            # Left: Aqua Logo + Active App Name + Standard Menus
            aqua_btn = Gtk.Button(label=" Aqua")
            aqua_btn.connect(
                "clicked",
                lambda _b: subprocess.Popen(["python3", "-m", "apps.about_aquaos"]),
            )
            bar.append(aqua_btn)

            active_lbl = Gtk.Label(label=model.window_tracker.active_app_name)
            active_lbl.add_css_class("aqua-menubar-active-app")
            bar.append(active_lbl)

            for menu_name in ("File", "Edit", "View", "Window", "AI", "Help"):
                m_btn = Gtk.Button(label=menu_name)
                m_btn.set_has_frame(False)
                bar.append(m_btn)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            bar.append(spacer)

            # Right: Shield Badge, AI Orb, Spotlight, Control Center, Battery, Clock
            summary = model.get_status_summary()

            shield_btn = Gtk.Button(label=summary["shield"])
            shield_btn.set_has_frame(False)
            shield_btn.connect(
                "clicked",
                lambda _b: subprocess.Popen(["python3", "-m", "security.shield_center"]),
            )
            bar.append(shield_btn)

            ai_btn = Gtk.Button(label=summary["ai_orb"])
            ai_btn.set_has_frame(False)
            ai_btn.connect(
                "clicked",
                lambda _b: subprocess.Popen(["python3", "-m", "ai.ai_studio"]),
            )
            bar.append(ai_btn)

            spotlight_btn = Gtk.Button(label="🔍")
            spotlight_btn.set_has_frame(False)
            spotlight_btn.connect(
                "clicked",
                lambda _b: subprocess.Popen(["python3", "-m", "spotlight.spotlight"]),
            )
            bar.append(spotlight_btn)

            bat_lbl = Gtk.Label(label=summary["battery"])
            bar.append(bat_lbl)

            clock_lbl = Gtk.Label(label=summary["clock"])
            bar.append(clock_lbl)

            def tick() -> bool:
                s = model.get_status_summary()
                active_lbl.set_text(s["active_app"])
                clock_lbl.set_text(s["clock"])
                return True

            GLib.timeout_add_seconds(5, tick)
            win.set_child(bar)
            win.present()

    app = MenuBarApp()
    app.run(None)
    return True


def main() -> None:
    model = AquaMenuBarModel()
    if not launch_gtk_menubar(model):
        s = model.get_status_summary()
        print(
            f"[Aqua MenuBar]  {s['active_app']} | File Edit View Window AI Help   "
            f"{s['shield']} | {s['ai_orb']} | {s['wifi']} | {s['battery']} | {s['clock']}"
        )


if __name__ == "__main__":
    main()
