"""Downloads and installs QEMU into user directory without requiring Administrator / UAC elevation."""
import os
import sys
import subprocess
import urllib.request
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\iamni\\AppData\\Local")) / "Programs" / "qemu"
TEMP_DIR = Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))
INSTALLER_URL = "https://qemu.weilnetz.de/w64/2026/qemu-w64-setup-20260811.exe"
INSTALLER_PATH = TEMP_DIR / "qemu-setup.exe"

def setup():
    qemu_bin = INSTALL_DIR / "qemu-system-x86_64.exe"
    if qemu_bin.exists():
        print(f"[+] QEMU already installed at: {qemu_bin}")
        return str(qemu_bin)

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not INSTALLER_PATH.exists() or INSTALLER_PATH.stat().st_size < 100_000_000:
        print(f"[*] Downloading QEMU installer from {INSTALLER_URL}...")
        def reporthook(blocknum, blocksize, totalsize):
            read = blocknum * blocksize
            if totalsize > 0 and blocknum % 500 == 0:
                pct = min(100.0, (read / totalsize) * 100)
                print(f"    Progress: {pct:.1f}% ({read // (1024*1024)} MB / {totalsize // (1024*1024)} MB)", flush=True)

        urllib.request.urlretrieve(INSTALLER_URL, str(INSTALLER_PATH), reporthook=reporthook)
        print(f"[+] Download complete: {INSTALLER_PATH.stat().st_size} bytes")

    # Extract without elevation using 7-zip
    z7_bin = TEMP_DIR / "7zip-bin" / "Files" / "7-Zip" / "7z.exe"
    if not z7_bin.exists():
        print("[*] Preparing elevation-free extraction engine...")
        msi_path = TEMP_DIR / "7z.msi"
        if not msi_path.exists():
            urllib.request.urlretrieve("https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.msi", str(msi_path))
        subprocess.run(["msiexec", "/a", str(msi_path), "/qn", f"TARGETDIR={TEMP_DIR / '7zip-bin'}"], check=True)

    print(f"[*] Extracting QEMU directly into: {INSTALL_DIR}...")
    extract_dir = TEMP_DIR / "qemu-extracted"
    subprocess.run([str(z7_bin), "x", str(INSTALLER_PATH), f"-o{extract_dir}", "-y"], check=True)

    for item in extract_dir.glob("*"):
        dest = INSTALL_DIR / item.name
        if item.is_dir():
            import shutil
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            import shutil
            shutil.copy2(item, dest)

    if qemu_bin.exists():
        print(f"[SUCCESS] QEMU executable verified: {qemu_bin}")
        return str(qemu_bin)
    else:
        print(f"[!] Warning: {qemu_bin} not found. Check installation directory.")
        return None

if __name__ == "__main__":
    setup()
