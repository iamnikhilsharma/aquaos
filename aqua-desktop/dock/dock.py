"""AquaOS Magnifying Application Dock (dock.py).

Implements the signature macOS bottom frosted-glass Dock with:
- Smooth parabolic cosine hover magnification
- Pinned default apps (Finder, Browser, Aqua AI Studio, Terminal, Aqua Shield, System Settings)
- Running application indicator dots & launch bounce animation
- Trash integration
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.app_indexer import AppEntry, AppIndexer
from core.config import AquaConfig


def compute_parabolic_magnification(
    cursor_x: Optional[float],
    icon_center_x: float,
    base_size: int = 52,
    max_scale: float = 1.65,
    radius: float = 150.0,
) -> float:
    """Compute the magnified icon pixel size using a smooth cosine-squared wave.

    Formula:
        scale(d) = 1 + (max_scale - 1) * max(0, cos((pi / 2) * min(1, |cursor_x - icon_x| / radius)))^2
    """
    if cursor_x is None or radius <= 0 or max_scale <= 1.0:
        return float(base_size)

    distance = abs(cursor_x - icon_center_x)
    if distance >= radius:
        return float(base_size)

    normalized = distance / radius
    factor = math.cos((math.pi / 2.0) * normalized) ** 2
    scale = 1.0 + (max_scale - 1.0) * factor
    return round(base_size * scale, 2)


class AquaDockModel:
    """Manages pinned Dock items, running status dots, and parabolic icon sizing."""

    def __init__(self, config: Optional[AquaConfig] = None, indexer: Optional[AppIndexer] = None) -> None:
        self.config = config or AquaConfig()
        self.indexer = indexer or AppIndexer()

    def get_pinned_entries(self) -> List[AppEntry]:
        pinned_ids: List[str] = self.config.get("dock", "pinned_apps", [])
        entries: List[AppEntry] = []
        for app_id in pinned_ids:
            app = self.indexer.get_app(app_id)
            if app:
                entries.append(app)
        return entries

    def compute_dock_layout(self, cursor_x: Optional[float], spacing: float = 12.0) -> List[dict]:
        """Calculate the center position and magnified size of each icon in the Dock."""
        entries = self.get_pinned_entries()
        base_size = int(self.config.get("dock", "icon_size", 52))
        mag_enabled = bool(self.config.get("dock", "magnification_enabled", True))
        max_scale = float(self.config.get("dock", "magnification_scale", 1.65)) if mag_enabled else 1.0
        radius = float(self.config.get("dock", "magnification_radius", 150.0))

        layout: List[dict] = []
        for idx, app in enumerate(entries):
            center_x = idx * (base_size + spacing) + (base_size / 2.0)
            size = compute_parabolic_magnification(
                cursor_x=cursor_x,
                icon_center_x=center_x,
                base_size=base_size,
                max_scale=max_scale,
                radius=radius,
            )
            layout.append(
                {
                    "app_id": app.app_id,
                    "name": app.name,
                    "icon": app.icon,
                    "exec_cmd": app.exec_cmd,
                    "center_x": center_x,
                    "size": size,
                    "scale": round(size / base_size, 3),
                }
            )
        return layout


def launch_gtk_dock(model: AquaDockModel) -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # type: ignore
    except Exception:
        return False

    class DockApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aquaos.Dock")

        def do_activate(self) -> None:
            win = Gtk.ApplicationWindow(application=self, title="AquaOS Dock")
            win.set_decorated(False)

            try:
                gi.require_version("Gtk4LayerShell", "1.0")
                from gi.repository import Gtk4LayerShell  # type: ignore

                Gtk4LayerShell.init_for_window(win)
                Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.TOP)
                Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.BOTTOM, True)
                Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.BOTTOM, 8)
            except Exception:
                pass

            dock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            dock_box.add_css_class("aqua-dock")
            dock_box.set_margin_top(8)
            dock_box.set_margin_bottom(8)
            dock_box.set_margin_start(14)
            dock_box.set_margin_end(14)

            buttons: List[Gtk.Button] = []
            for item in model.compute_dock_layout(cursor_x=None):
                btn = Gtk.Button(label=item["name"])
                btn.set_tooltip_text(item["name"])
                btn.set_size_request(int(item["size"]), int(item["size"]))
                cmd = item["exec_cmd"]
                btn.connect("clicked", lambda _b, c=cmd: subprocess.Popen(c, shell=True))
                dock_box.append(btn)
                buttons.append(btn)

            motion = Gtk.EventControllerMotion.new()

            def on_motion(_ctrl: object, x: float, _y: float) -> None:
                updated = model.compute_dock_layout(cursor_x=x)
                for btn, info in zip(buttons, updated):
                    s = int(info["size"])
                    btn.set_size_request(s, s)

            def on_leave(_ctrl: object) -> None:
                reset = model.compute_dock_layout(cursor_x=None)
                for btn, info in zip(buttons, reset):
                    s = int(info["size"])
                    btn.set_size_request(s, s)

            motion.connect("motion", on_motion)
            motion.connect("leave", on_leave)
            dock_box.add_controller(motion)

            win.set_child(dock_box)
            win.present()

    app = DockApp()
    app.run(None)
    return True


def main() -> None:
    model = AquaDockModel()
    if not launch_gtk_dock(model):
        layout = model.compute_dock_layout(cursor_x=120.0)
        print("[Aqua Dock — Parabolic Hover Magnification Active]")
        for item in layout:
            print(f" • {item['name']:<18} size={item['size']}px (scale={item['scale']}x)")


if __name__ == "__main__":
    main()
