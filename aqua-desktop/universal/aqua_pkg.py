"""Aqua Universal Package Manager (aqua_pkg.py).

Allows installing packages from any Linux ecosystem without polluting the immutable base OS:
- Debian / Ubuntu (.deb / apt)
- Flatpak (Flathub)
- Fedora / RHEL (.rpm via rootless Distrobox fedora container)
- Arch Linux / AUR (.pkg.tar.zst / yay via rootless Distrobox arch container)
- macOS .app bundles (copied to ~/Applications)
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class PackageActionPlan:
    """Describes how aqua-pkg will install or search a package across ecosystems."""

    action: str  # "install" | "search" | "list"
    target: str
    backend: str  # "apt" | "flatpak" | "distrobox-arch" | "distrobox-fedora" | "mac-bundle"
    command: List[str]


class AquaPackageManager:
    """Unified cross-distro package manager for AquaOS."""

    def plan_install(self, target: str, preferred_distro: Optional[str] = None) -> PackageActionPlan:
        path = Path(target)
        suffix = path.suffix.lower()
        name_lower = path.name.lower()

        if suffix == ".app" and path.is_dir():
            dest = Path.home() / "Applications"
            return PackageActionPlan(
                action="install",
                target=target,
                backend="mac-bundle",
                command=["cp", "-r", str(path), str(dest / path.name)],
            )

        if suffix == ".deb":
            return PackageActionPlan(
                action="install",
                target=target,
                backend="apt",
                command=["sudo", "apt-get", "install", "-y", str(path)],
            )

        if suffix == ".rpm" or preferred_distro == "fedora":
            return PackageActionPlan(
                action="install",
                target=target,
                backend="distrobox-fedora",
                command=[
                    "distrobox-enter",
                    "aqua-fedora",
                    "--",
                    "sudo",
                    "dnf",
                    "install",
                    "-y",
                    target,
                ],
            )

        if name_lower.endswith(".pkg.tar.zst") or preferred_distro == "arch":
            cmd_op = ["-U", "--noconfirm", target] if name_lower.endswith(".pkg.tar.zst") else ["-S", "--noconfirm", target]
            return PackageActionPlan(
                action="install",
                target=target,
                backend="distrobox-arch",
                command=["distrobox-enter", "aqua-arch", "--", "sudo", "pacman", *cmd_op],
            )

        if suffix == ".flatpakref" or "." in target and target.count(".") >= 2:
            return PackageActionPlan(
                action="install",
                target=target,
                backend="flatpak",
                command=["flatpak", "install", "-y", target],
            )

        return PackageActionPlan(
            action="install",
            target=target,
            backend="apt",
            command=["sudo", "apt-get", "install", "-y", target],
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2 or args[0] != "install":
        print("Usage: aqua-pkg install <package-name | file.deb | file.rpm | file.pkg.tar.zst | org.app.Flatpak | App.app>")
        return 1

    mgr = AquaPackageManager()
    plan = mgr.plan_install(args[1])
    print(f"[Aqua Universal Package Manager] Backend={plan.backend} -> {' '.join(plan.command)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
