"""About AquaOS Dialog (about_aquaos.py).

Authentic "About This Mac" style overview modal showing AquaOS version, codename,
processor, memory, GPU & VRAM, Neural Engine status, and Immutable RootFS status.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.neural_boost import NeuralBoostManager
from core.system_services import SystemServices


def get_about_info() -> Dict[str, str]:
    services = SystemServices()
    boost = NeuralBoostManager()
    specs = services.get_hardware_specs()
    nb_status = boost.status()
    return {
        "OS Name": specs.os_name,
        "Kernel": f"Linux {specs.kernel_version} (AI HugePages + Lockdown)",
        "Host": specs.hostname,
        "Processor": f"{specs.cpu_model} ({specs.cpu_cores} cores)",
        "Memory": f"{specs.ram_total_gb:.1f} GB LPDDR5/DDR5 ({specs.ram_available_gb:.1f} GB Available)",
        "Graphics": f"{specs.gpu_model} ({specs.vram_total_gb:.1f} GB VRAM)",
        "Neural Engine": f"Active ({nb_status.gpu_backend.upper()} • Flash Attention • KV {nb_status.kv_cache_type})",
        "Security": "Immutable SquashFS Root + Aqua Shield Bubblewrap Sandbox",
        "Startup Disk": f"AquaOS Root ({specs.disk_free_gb:.1f} GB free of {specs.disk_total_gb:.1f} GB)",
    }


def launch_gtk_about() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # type: ignore
    except Exception:
        return False

    class AboutApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aquaos.About")

        def do_activate(self) -> None:
            win = Gtk.ApplicationWindow(application=self, title="About AquaOS")
            win.set_default_size(420, 460)
            win.set_resizable(False)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(24)
            box.set_margin_bottom(24)
            box.set_margin_start(28)
            box.set_margin_end(28)

            title = Gtk.Label(label=" AquaOS")
            title.add_css_class("title-1")
            box.append(title)

            sub = Gtk.Label(label="Version 1.0 Beta (Sonoma-AI • Virus-Proof Edition)")
            box.append(sub)

            for k, v in get_about_info().items():
                row = Gtk.Label(label=f"{k}: {v}")
                row.set_xalign(0.0)
                box.append(row)

            win.set_child(box)
            win.present()

    app = AboutApp()
    app.run(None)
    return True


def main() -> None:
    if not launch_gtk_about():
        print("=== About AquaOS ===")
        for k, v in get_about_info().items():
            print(f"  {k:<15}: {v}")


if __name__ == "__main__":
    main()
