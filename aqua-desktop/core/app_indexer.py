"""AquaOS Universal Application Indexer.

Parses and indexes:
- Standard FreeDesktop .desktop files (/usr/share/applications, ~/.local/share/applications, Flatpak)
- macOS-style .app bundles (/Applications, ~/Applications)
- Portable .AppImage binaries and Windows .exe shortcuts
Provides fast fuzzy search and ranking for Spotlight and the Dock.
"""

from __future__ import annotations

import configparser
import os
import plistlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class AppEntry:
    """Represents a launchable application in AquaOS."""

    app_id: str
    name: str
    exec_cmd: str
    icon: str = "application-x-executable"
    comment: str = ""
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    app_type: str = "native"  # "native" | "mac_bundle" | "flatpak" | "appimage" | "windows"
    path: str = ""
    sandboxed: bool = False


BUILTIN_AQUA_APPS: List[AppEntry] = [
    AppEntry(
        app_id="org.aquaos.Finder",
        name="Finder",
        exec_cmd="nautilus",
        icon="system-file-manager",
        comment="Browse files, folders, .app bundles, and disks",
        categories=["System", "FileManager"],
        keywords=["files", "folders", "finder", "disk"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.Browser",
        name="Safari (Aqua Web)",
        exec_cmd="firefox-esr",
        icon="web-browser",
        comment="Browse the web with privacy and sandboxing",
        categories=["Network", "WebBrowser"],
        keywords=["web", "internet", "browser", "safari", "firefox"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.AIStudio",
        name="Aqua AI Studio",
        exec_cmd="python3 -m ai.ai_studio",
        icon="applications-science",
        comment="Local LLM Chat, Model Hub, VRAM Estimator, and Sandboxed AI Agent",
        categories=["AI", "Development", "Science"],
        keywords=["ai", "llm", "ollama", "deepseek", "llama", "qwen", "neural", "chat"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.Terminal",
        name="Terminal",
        exec_cmd="foot",
        icon="utilities-terminal",
        comment="Command line shell and system terminal",
        categories=["System", "TerminalEmulator"],
        keywords=["shell", "bash", "zsh", "cli", "console", "terminal"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.ShieldCenter",
        name="Aqua Shield",
        exec_cmd="python3 -m security.shield_center",
        icon="security-high",
        comment="Zero-Trust Security Center, Gatekeeper, Sandbox Manager & Malware Scanner",
        categories=["System", "Security"],
        keywords=["security", "virus", "antivirus", "sandbox", "firewall", "gatekeeper", "shield"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.SystemSettings",
        name="System Settings",
        exec_cmd="python3 -m apps.system_settings",
        icon="preferences-system",
        comment="Configure Appearance, Dock, Wallpaper, AI Compute, and Security",
        categories=["Settings", "System"],
        keywords=["settings", "preferences", "control", "dock", "theme", "dark mode", "display"],
        app_type="native",
    ),
    AppEntry(
        app_id="org.aquaos.About",
        name="About AquaOS",
        exec_cmd="python3 -m apps.about_aquaos",
        icon="computer",
        comment="System hardware overview, kernel, GPU, and OS version",
        categories=["System"],
        keywords=["about", "hardware", "version", "specs", "mac"],
        app_type="native",
    ),
]


class AppIndexer:
    """Indexes applications across Linux, macOS .app bundles, AppImages, and Wine."""

    def __init__(self, extra_dirs: Optional[List[Path]] = None) -> None:
        self._apps: Dict[str, AppEntry] = {}
        self.search_dirs: List[Path] = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/applications",
            Path.home() / ".local/share/flatpak/exports/share/applications",
        ]
        self.bundle_dirs: List[Path] = [
            Path("/Applications"),
            Path.home() / "Applications",
        ]
        if extra_dirs:
            self.search_dirs.extend(extra_dirs)
        self.refresh()

    def refresh(self) -> List[AppEntry]:
        """Scan all application directories and rebuild the index."""
        self._apps.clear()
        for app in BUILTIN_AQUA_APPS:
            self._apps[app.app_id] = app

        for directory in self.search_dirs:
            if directory.exists() and directory.is_dir():
                for desktop_file in directory.glob("*.desktop"):
                    entry = self.parse_desktop_file(desktop_file)
                    if entry and entry.app_id not in self._apps:
                        self._apps[entry.app_id] = entry

        for bundle_dir in self.bundle_dirs:
            if bundle_dir.exists() and bundle_dir.is_dir():
                for item in bundle_dir.iterdir():
                    if item.suffix.lower() == ".app" and item.is_dir():
                        entry = self.parse_mac_app_bundle(item)
                        if entry:
                            self._apps[entry.app_id] = entry
                    elif item.suffix.lower() == ".appimage" and item.is_file():
                        app_id = f"appimage.{item.stem}"
                        self._apps[app_id] = AppEntry(
                            app_id=app_id,
                            name=item.stem.replace("-", " ").replace("_", " ").title(),
                            exec_cmd=f"aqua-run \"{item}\"",
                            icon="application-x-executable",
                            comment=f"Portable AppImage ({item.name})",
                            app_type="appimage",
                            path=str(item),
                            sandboxed=True,
                        )
        return list(self._apps.values())

    @staticmethod
    def parse_desktop_file(path: Path) -> Optional[AppEntry]:
        """Parse a FreeDesktop .desktop file into an AppEntry."""
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(path, encoding="utf-8")
        except Exception:
            return None

        if "Desktop Entry" not in cp:
            return None

        section = cp["Desktop Entry"]
        if section.get("NoDisplay", "false").lower() == "true":
            return None
        if section.get("Hidden", "false").lower() == "true":
            return None

        name = section.get("Name", "").strip()
        exec_raw = section.get("Exec", "").strip()
        if not name or not exec_raw:
            return None

        # Strip FreeDesktop field codes (%U, %F, %u, %f, etc.)
        exec_tokens = [tok for tok in exec_raw.split() if not tok.startswith("%")]
        exec_cmd = " ".join(exec_tokens)

        icon = section.get("Icon", "application-x-executable").strip()
        comment = section.get("Comment", "").strip()
        categories = [c for c in section.get("Categories", "").split(";") if c]
        keywords = [k for k in section.get("Keywords", "").split(";") if k]
        is_flatpak = "flatpak" in exec_cmd or "flatpak" in str(path)

        return AppEntry(
            app_id=path.stem,
            name=name,
            exec_cmd=exec_cmd,
            icon=icon,
            comment=comment,
            categories=categories,
            keywords=keywords,
            app_type="flatpak" if is_flatpak else "native",
            path=str(path),
            sandboxed=is_flatpak,
        )

    @staticmethod
    def parse_mac_app_bundle(bundle_path: Path) -> Optional[AppEntry]:
        """Parse a macOS-style .app directory (Contents/Info.plist)."""
        info_plist = bundle_path / "Contents" / "Info.plist"
        name = bundle_path.stem
        bundle_id = f"mac.{bundle_path.stem.lower()}"
        executable = bundle_path.stem

        if info_plist.exists():
            try:
                with info_plist.open("rb") as f:
                    plist_data = plistlib.load(f)
                name = plist_data.get("CFBundleDisplayName") or plist_data.get("CFBundleName") or name
                bundle_id = plist_data.get("CFBundleIdentifier") or bundle_id
                executable = plist_data.get("CFBundleExecutable") or executable
            except Exception:
                pass

        return AppEntry(
            app_id=bundle_id,
            name=name,
            exec_cmd=f"aqua-run \"{bundle_path}\"",
            icon="application-x-addon",
            comment=f"macOS Application Bundle ({bundle_path.name})",
            categories=["macOS", "Universal"],
            keywords=[name.lower(), executable.lower(), "macos", "app"],
            app_type="mac_bundle",
            path=str(bundle_path),
            sandboxed=True,
        )

    def search(self, query: str, limit: int = 10) -> List[AppEntry]:
        """Fuzzy-search indexed applications and return top matches sorted by relevance."""
        q = query.strip().lower()
        if not q:
            return list(self._apps.values())[:limit]

        scored: List[tuple[int, AppEntry]] = []
        for app in self._apps.values():
            score = self._score_match(q, app)
            if score > 0:
                scored.append((score, app))

        scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
        return [item[1] for item in scored[:limit]]

    def get_app(self, app_id: str) -> Optional[AppEntry]:
        return self._apps.get(app_id)

    def all_apps(self) -> List[AppEntry]:
        return list(self._apps.values())

    @staticmethod
    def _score_match(query: str, app: AppEntry) -> int:
        name_lower = app.name.lower()
        if name_lower == query:
            return 100
        if name_lower.startswith(query):
            return 85
        if query in name_lower:
            return 70
        for kw in app.keywords:
            if query in kw.lower():
                return 60
        if query in app.comment.lower():
            return 45
        if query in app.app_id.lower():
            return 35
        # Subsequence fuzzy match
        q_idx = 0
        for ch in name_lower:
            if q_idx < len(query) and ch == query[q_idx]:
                q_idx += 1
        if q_idx == len(query):
            return 25
        return 0
