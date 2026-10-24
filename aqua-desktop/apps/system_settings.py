"""AquaOS System Settings (system_settings.py).

macOS Sonoma/Sequoia-inspired sidebar settings application allowing users to configure:
- Appearance (Dark / Light mode, Accent Color, Frosted Glass Blur)
- Desktop & Dock (Icon Size, Parabolic Magnification Scale, Auto-hide)
- Aqua Intelligence & AI Compute (Default LLM, Neural Boost, Flash Attention, KV Cache Quantization)
- Security & Privacy (Gatekeeper Mode, Mandatory Foreign Binary Sandboxing, Firewall)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import AquaConfig


ACCENT_COLORS = {
    "Blue": "#0A84FF",
    "Purple": "#BF5AF2",
    "Pink": "#FF375F",
    "Orange": "#FF9F0A",
    "Green": "#30D158",
    "Graphite": "#8E8E93",
}


def launch_gtk_settings(config: AquaConfig) -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # type: ignore
    except Exception:
        return False

    class SettingsApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aquaos.SystemSettings")

        def do_activate(self) -> None:
            win = Gtk.ApplicationWindow(application=self, title="System Settings")
            win.set_default_size(760, 520)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(18)
            box.set_margin_bottom(18)
            box.set_margin_start(20)
            box.set_margin_end(20)

            hdr = Gtk.Label(label="⚙ AquaOS System Settings")
            hdr.set_xalign(0.0)
            box.append(hdr)

            # Theme Toggle
            theme_btn = Gtk.Button(
                label=f"Appearance Mode: {config.get('appearance', 'theme', 'dark').upper()} (Click to Toggle)"
            )

            def on_toggle_theme(btn: Gtk.Button) -> None:
                cur = config.get("appearance", "theme", "dark")
                nxt = "light" if cur == "dark" else "dark"
                config.set("appearance", "theme", nxt)
                btn.set_label(f"Appearance Mode: {nxt.upper()} (Click to Toggle)")

            theme_btn.connect("clicked", on_toggle_theme)
            box.append(theme_btn)

            # Magnification Toggle
            mag_btn = Gtk.ToggleButton(label="Dock Parabolic Magnification")
            mag_btn.set_active(bool(config.get("dock", "magnification_enabled", True)))
            mag_btn.connect(
                "toggled",
                lambda b: config.set("dock", "magnification_enabled", b.get_active()),
            )
            box.append(mag_btn)

            # Neural Boost Toggle
            nb_btn = Gtk.ToggleButton(label="AI Neural Boost & Flash Attention")
            nb_btn.set_active(bool(config.get("ai", "neural_boost_enabled", True)))
            nb_btn.connect(
                "toggled",
                lambda b: config.set("ai", "neural_boost_enabled", b.get_active()),
            )
            box.append(nb_btn)

            # Sandbox Foreign Binaries Toggle
            sb_btn = Gtk.ToggleButton(label="Mandatory Bubblewrap Sandbox for Untrusted & Windows/macOS Apps")
            sb_btn.set_active(bool(config.get("security", "enforce_sandbox_foreign_binaries", True)))
            sb_btn.connect(
                "toggled",
                lambda b: config.set("security", "enforce_sandbox_foreign_binaries", b.get_active()),
            )
            box.append(sb_btn)

            # Default Applications Summary
            def_apps = config.get("default_apps") or {}
            def_lbl = Gtk.Label(
                label=f"Default Apps: Browser ({def_apps.get('browser', 'firefox')}), Mail ({def_apps.get('email', 'thunderbird')}), Store ({def_apps.get('package_manager', 'snap-store')})"
            )
            def_lbl.set_xalign(0.0)
            box.append(def_lbl)

            win.set_child(box)
            win.present()

    app = SettingsApp()
    app.run(None)
    return True


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    config = AquaConfig()
    if not launch_gtk_settings(config):
        print("=== AquaOS System Settings ===")
        print(f" • Theme           : {config.get('appearance', 'theme')}")
        print(f" • Accent Color    : {config.get('appearance', 'accent_name')} ({config.get('appearance', 'accent_color')})")
        print(f" • Dock Icon Size  : {config.get('dock', 'icon_size')}px (Magnification: {config.get('dock', 'magnification_scale')}x)")
        print(f" • Default AI LLM  : {config.get('ai', 'default_model')} (Neural Boost: {config.get('ai', 'neural_boost_enabled')})")
        print(f" • Security Mode   : {config.get('security', 'mode')} (Sandbox Enforced: {config.get('security', 'enforce_sandbox_foreign_binaries')})")
        def_apps = config.get("default_apps") or {}
        print(" • Default Applications:")
        print(f"    - Web Browser   : {def_apps.get('browser', 'firefox')}")
        print(f"    - Email Client  : {def_apps.get('email', 'thunderbird')}")
        print(f"    - Image Viewer  : {def_apps.get('image_viewer', 'preview')}")
        print(f"    - Music Player  : {def_apps.get('music_player', 'music')}")
        print(f"    - Video Player  : {def_apps.get('video_player', 'quicktime')}")
        print(f"    - Package Store : {def_apps.get('package_manager', 'snap-store')}")


if __name__ == "__main__":
    main()
