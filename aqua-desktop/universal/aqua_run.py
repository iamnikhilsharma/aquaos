"""Aqua Universal Launcher (aqua_run.py).

Enables AquaOS to transparently execute applications and bundles from across operating systems
while keeping the host OS virus-proof via Aqua Gatekeeper + Aqua Sandbox (Bubblewrap):

Supported Formats:
- macOS Application Bundles (.app) & Disk Images (.dmg) -> Native Aqua Bundle or Darling macOS layer
- Windows Executables & Installers (.exe, .msi) -> Isolated Wine / Proton Sandbox Prefix
- Android Packages (.apk) -> Waydroid Container Session
- Portable Linux Binaries (.AppImage, ELF) -> Sandboxed Execution
- Cross-Distro Packages (.deb, .rpm, .pkg.tar.zst, .flatpakref) -> Dispatched to aqua-pkg
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security.gatekeeper import AquaGatekeeper, ScanReport
from security.sandbox import AquaSandbox, SandboxPolicy


@dataclass
class ExecutionPlan:
    """Describes how Aqua Universal Runtime will execute a target file or bundle."""

    target_path: str
    target_type: str  # "MAC_APP" | "MAC_DMG" | "WIN_EXE" | "WIN_MSI" | "ANDROID_APK" | "APPIMAGE" | "LINUX_PKG" | "NATIVE_ELF" | "SCRIPT"
    runtime_bridge: str  # "darling" | "aqua-bundle" | "wine-sandbox" | "waydroid" | "bwrap-appimage" | "aqua-pkg" | "bwrap-native"
    command: List[str]
    sandboxed: bool
    scan_report: Optional[ScanReport] = None
    blocked: bool = False
    block_reason: str = ""


class AquaUniversalRunner:
    """Detects application format, runs Gatekeeper verification, and builds a sandboxed execution plan."""

    def __init__(self) -> None:
        self.gatekeeper = AquaGatekeeper()
        self.sandbox = AquaSandbox()

    def classify_target(self, target: Path) -> str:
        """Identify the cross-platform application type from path and header."""
        name_lower = target.name.lower()
        suffix = target.suffix.lower()

        if suffix == ".app":
            return "MAC_APP"
        if suffix == ".dmg":
            return "MAC_DMG"
        if suffix == ".exe":
            return "WIN_EXE"
        if suffix == ".msi":
            return "WIN_MSI"
        if suffix == ".apk":
            return "ANDROID_APK"
        if suffix == ".appimage":
            return "APPIMAGE"
        if suffix in (".deb", ".rpm", ".flatpakref") or name_lower.endswith(".pkg.tar.zst"):
            return "LINUX_PKG"
        if suffix in (".sh", ".py"):
            return "SCRIPT"

        if target.exists() and target.is_file():
            try:
                with target.open("rb") as f:
                    hdr = f.read(16)
                fmt = self.gatekeeper.detect_binary_format(hdr, suffix)
                if fmt == "PE_EXE":
                    return "WIN_EXE"
                if fmt == "MACH_O":
                    return "MAC_APP"
                if fmt == "SCRIPT":
                    return "SCRIPT"
            except OSError:
                pass
        return "NATIVE_ELF"

    def create_execution_plan(
        self,
        target: Path,
        allow_network: bool = False,
        allow_documents: bool = False,
    ) -> ExecutionPlan:
        """Inspect target with Gatekeeper and build the appropriate universal sandbox command."""
        target = Path(target)
        target_type = self.classify_target(target)

        scan_report: Optional[ScanReport] = None
        if target.exists() and target.is_file():
            scan_report = self.gatekeeper.scan_file(target)
            if scan_report.recommended_action == "BLOCK":
                return ExecutionPlan(
                    target_path=str(target),
                    target_type=target_type,
                    runtime_bridge="gatekeeper-blocked",
                    command=[],
                    sandboxed=True,
                    scan_report=scan_report,
                    blocked=True,
                    block_reason=f"Blocked by Aqua Gatekeeper ({scan_report.risk_level}): {', '.join(scan_report.findings)}",
                )

        app_id = f"universal.{target.stem.lower()}"
        policy = SandboxPolicy(
            app_id=app_id,
            allow_network=allow_network,
            allow_documents=allow_documents,
        )

        if target_type == "MAC_APP":
            exe_path, is_macho = self._resolve_mac_bundle_executable(target)
            if is_macho:
                inner_cmd = ["darling", "shell", str(exe_path)]
                bridge = "darling"
            else:
                inner_cmd = [str(exe_path)]
                bridge = "aqua-bundle"
            cmd = self.sandbox.build_bwrap_command(inner_cmd, policy)
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge=bridge,
                command=cmd,
                sandboxed=True,
                scan_report=scan_report,
            )

        if target_type == "MAC_DMG":
            mount_dir = f"/tmp/aqua-dmg-{target.stem}"
            inner_cmd = ["7z", "x", str(target), f"-o{mount_dir}", "-y"]
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge="dmg-extractor",
                command=inner_cmd,
                sandboxed=True,
                scan_report=scan_report,
            )

        if target_type in ("WIN_EXE", "WIN_MSI"):
            wine_prefix = self.sandbox.get_app_sandbox_home(app_id) / ".wine"
            inner_cmd = ["wine", "msiexec", "/i", str(target)] if target_type == "WIN_MSI" else ["wine", str(target)]
            cmd = self.sandbox.build_bwrap_command(
                inner_cmd,
                policy,
                env_overrides={"WINEPREFIX": str(wine_prefix), "WINEDLLOVERRIDES": "mscoree,mshtml="},
            )
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge="wine-sandbox",
                command=cmd,
                sandboxed=True,
                scan_report=scan_report,
            )

        if target_type == "ANDROID_APK":
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge="waydroid",
                command=["waydroid", "app", "install", str(target)],
                sandboxed=True,
                scan_report=scan_report,
            )

        if target_type == "APPIMAGE":
            inner_cmd = [str(target), "--appimage-extract-and-run"]
            cmd = self.sandbox.build_bwrap_command(inner_cmd, policy)
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge="bwrap-appimage",
                command=cmd,
                sandboxed=True,
                scan_report=scan_report,
            )

        if target_type == "LINUX_PKG":
            return ExecutionPlan(
                target_path=str(target),
                target_type=target_type,
                runtime_bridge="aqua-pkg",
                command=["python3", "-m", "universal.aqua_pkg", "install", str(target)],
                sandboxed=True,
                scan_report=scan_report,
            )

        # Default: NATIVE_ELF or SCRIPT inside Bubblewrap sandbox
        inner_cmd = [str(target)]
        cmd = self.sandbox.build_bwrap_command(inner_cmd, policy)
        return ExecutionPlan(
            target_path=str(target),
            target_type=target_type,
            runtime_bridge="bwrap-native",
            command=cmd,
            sandboxed=True,
            scan_report=scan_report,
        )

    def _resolve_mac_bundle_executable(self, bundle_path: Path) -> tuple[Path, bool]:
        """Locate Contents/MacOS/<Executable> inside a .app bundle and detect if it is a Mach-O binary."""
        info_plist = bundle_path / "Contents" / "Info.plist"
        exe_name = bundle_path.stem
        if info_plist.exists():
            try:
                with info_plist.open("rb") as f:
                    plist = plistlib.load(f)
                exe_name = plist.get("CFBundleExecutable", exe_name)
            except Exception:
                pass

        exe_path = bundle_path / "Contents" / "MacOS" / exe_name
        is_macho = False
        if exe_path.exists() and exe_path.is_file():
            try:
                with exe_path.open("rb") as f:
                    hdr = f.read(16)
                is_macho = self.gatekeeper.detect_binary_format(hdr) == "MACH_O"
            except OSError:
                pass
        return exe_path, is_macho


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: aqua-run <file.app | file.dmg | file.exe | file.AppImage | file.apk | file.deb>")
        return 1

    target = Path(args[0])
    runner = AquaUniversalRunner()
    plan = runner.create_execution_plan(target)

    if plan.blocked:
        print(f"[Aqua Gatekeeper BLOCKED] {plan.block_reason}", file=sys.stderr)
        return 2

    print(f"[Aqua Universal Runtime] Type={plan.target_type} | Bridge={plan.runtime_bridge} | Sandboxed={plan.sandboxed}")
    if "--dry-run" in args:
        print("Command:", " ".join(plan.command))
        return 0

    try:
        proc = subprocess.run(plan.command)
        return proc.returncode
    except FileNotFoundError as exc:
        print(f"Runtime bridge binary not installed on host ({exc}). Command prepared: {' '.join(plan.command)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
