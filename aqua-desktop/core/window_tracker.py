"""AquaOS Window & Toplevel Tracker.

Tracks active windows across Wayland (wlr-foreign-toplevel / labwc) and X11 (wmctrl / xprop),
providing active application title and standard menu actions for the Global Menu Bar and Dock.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class WindowInfo:
    """Metadata for an open desktop window."""

    window_id: str
    app_id: str
    title: str
    pid: int = 0
    is_active: bool = False
    is_minimized: bool = False
    is_sandboxed: bool = False


class WindowTracker:
    """Queries and controls desktop windows across Wayland and X11."""

    def __init__(self) -> None:
        self._windows: List[WindowInfo] = []
        self._active_app_name: str = "Finder"
        self._active_window_title: str = "Desktop"

    def refresh(self) -> List[WindowInfo]:
        """Refresh list of running windows using wlrctl (Wayland) or wmctrl (X11)."""
        windows: List[WindowInfo] = []

        if shutil.which("wlrctl"):
            try:
                out = subprocess.check_output(
                    ["wlrctl", "toplevel", "list"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.0,
                )
                for idx, line in enumerate(out.splitlines()):
                    if ":" in line:
                        app_id, title = line.split(":", 1)
                        windows.append(
                            WindowInfo(
                                window_id=str(idx),
                                app_id=app_id.strip(),
                                title=title.strip(),
                                is_active=(idx == 0),
                            )
                        )
            except Exception:
                pass
        elif shutil.which("wmctrl"):
            try:
                out = subprocess.check_output(
                    ["wmctrl", "-lp"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.0,
                )
                for idx, line in enumerate(out.splitlines()):
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        win_id, _desktop, pid_str, _host, title = parts
                        windows.append(
                            WindowInfo(
                                window_id=win_id,
                                app_id=title.split("-")[-1].strip(),
                                title=title.strip(),
                                pid=int(pid_str) if pid_str.isdigit() else 0,
                                is_active=(idx == 0),
                            )
                        )
            except Exception:
                pass

        self._windows = windows
        if windows:
            active = next((w for w in windows if w.is_active), windows[0])
            self._active_app_name = self._format_app_name(active.app_id)
            self._active_window_title = active.title
        else:
            self._active_app_name = "Finder"
            self._active_window_title = "Desktop"
        return windows

    @property
    def active_app_name(self) -> str:
        return self._active_app_name

    @property
    def active_window_title(self) -> str:
        return self._active_window_title

    def running_app_ids(self) -> List[str]:
        """Return list of currently open application identifiers."""
        return [w.app_id.lower() for w in self._windows]

    def get_app_menus(self, app_name: Optional[str] = None) -> Dict[str, List[tuple[str, str]]]:
        """Return macOS-style Global Menu Bar structure for the active application."""
        target = app_name or self._active_app_name
        return {
            target: [
                (f"About {target}", "app.about"),
                ("Settings...", "app.settings"),
                ("Run in Aqua Sandbox", "app.sandbox"),
                ("Hide " + target, "window.minimize"),
                ("Quit " + target, "window.close"),
            ],
            "File": [
                ("New Window", "file.new_window"),
                ("Open via Universal Launcher...", "file.open_universal"),
                ("Close Window", "window.close"),
            ],
            "Edit": [
                ("Undo", "edit.undo"),
                ("Redo", "edit.redo"),
                ("Cut", "edit.cut"),
                ("Copy", "edit.copy"),
                ("Paste", "edit.paste"),
            ],
            "View": [
                ("Toggle Full Screen", "window.fullscreen"),
                ("Toggle Dark Mode", "system.toggle_theme"),
            ],
            "Window": [
                ("Minimize", "window.minimize"),
                ("Zoom / Maximize", "window.maximize"),
                ("Bring All to Front", "window.front"),
            ],
            "AI": [
                ("Ask Aqua Intelligence...", "ai.spotlight"),
                ("Open Aqua AI Studio", "ai.studio"),
                ("Toggle Neural Boost Mode", "ai.neural_boost"),
            ],
            "Help": [
                ("AquaOS Security & Sandbox Guide", "help.security"),
                ("System Diagnostics", "help.about"),
            ],
        }

    @staticmethod
    def _format_app_name(raw_id: str) -> str:
        if not raw_id:
            return "Finder"
        cleaned = raw_id.split(".")[-1].replace("-", " ").replace("_", " ").strip()
        return cleaned.title() if cleaned else "Finder"
