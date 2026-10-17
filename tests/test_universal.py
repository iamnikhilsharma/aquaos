"""Automated tests for Aqua Universal Runtime (aqua-run & aqua-pkg)."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aqua-desktop"))

from universal.aqua_pkg import AquaPackageManager
from universal.aqua_run import AquaUniversalRunner


def test_universal_runner_formats(tmp_path: Path) -> None:
    runner = AquaUniversalRunner()

    # 1. Windows .exe
    exe_file = tmp_path / "game.exe"
    exe_file.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    plan_exe = runner.create_execution_plan(exe_file)
    assert plan_exe.target_type == "WIN_EXE"
    assert plan_exe.runtime_bridge == "wine-sandbox"
    assert plan_exe.sandboxed is True
    assert not plan_exe.blocked

    # 2. macOS .app bundle
    app_bundle = tmp_path / "Calculator.app"
    macos_dir = app_bundle / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    with (app_bundle / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleName": "Calculator", "CFBundleExecutable": "calc-bin"}, f)
    (macos_dir / "calc-bin").write_bytes(b"\xcf\xfa\xed\xfe\x07\x00\x00\x01")

    plan_mac = runner.create_execution_plan(app_bundle)
    assert plan_mac.target_type == "MAC_APP"
    assert plan_mac.runtime_bridge == "darling"
    assert plan_mac.sandboxed is True

    # 3. Android .apk
    apk_file = tmp_path / "messenger.apk"
    apk_file.write_bytes(b"PK\x03\x04")
    plan_apk = runner.create_execution_plan(apk_file)
    assert plan_apk.target_type == "ANDROID_APK"
    assert plan_apk.runtime_bridge == "waydroid"

    # 4. Portable .AppImage
    appimage = tmp_path / "Krita.AppImage"
    appimage.write_bytes(b"\x7fELF\x02\x01\x01\x00")
    plan_ai = runner.create_execution_plan(appimage)
    assert plan_ai.target_type == "APPIMAGE"
    assert plan_ai.runtime_bridge == "bwrap-appimage"


def test_universal_runner_blocks_malware(tmp_path: Path) -> None:
    runner = AquaUniversalRunner()
    infected_exe = tmp_path / "miner.exe"
    infected_exe.write_bytes(b"MZ\x90\x00stratum+tcp://pool.evil:3333 xmrig VirtualAllocEx")
    plan = runner.create_execution_plan(infected_exe)
    assert plan.blocked is True
    assert plan.runtime_bridge == "gatekeeper-blocked"


def test_universal_package_manager() -> None:
    mgr = AquaPackageManager()
    assert mgr.plan_install("htop.deb").backend == "apt"
    assert mgr.plan_install("blender.rpm").backend == "distrobox-fedora"
    assert mgr.plan_install("neovim-git.pkg.tar.zst").backend == "distrobox-arch"
    assert mgr.plan_install("org.gimp.GIMP").backend == "flatpak"
