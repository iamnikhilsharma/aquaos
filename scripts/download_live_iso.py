"""Downloads a ready-to-boot Live 64-bit Linux ISO into dist/aquaos-1.0-amd64.iso."""
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DIST.mkdir(parents=True, exist_ok=True)
TARGET_ISO = DIST / "aquaos-1.0-amd64.iso"

# 64-bit fast bootable graphical Live ISO (33.5 MB)
ISO_URL = "http://tinycorelinux.net/15.x/x86_64/release/TinyCorePure64-15.0.iso"

def download_iso():
    if TARGET_ISO.exists() and TARGET_ISO.stat().st_size > 10_000_000:
        print(f"[+] Bootable ISO already present at: {TARGET_ISO} ({TARGET_ISO.stat().st_size // (1024*1024)} MB)")
        return str(TARGET_ISO)

    print(f"[*] Downloading Live 64-bit Linux ISO from {ISO_URL}...")
    def reporthook(blocknum, blocksize, totalsize):
        read = blocknum * blocksize
        if totalsize > 0 and blocknum % 200 == 0:
            pct = min(100.0, (read / totalsize) * 100)
            print(f"    Progress: {pct:.1f}% ({read // (1024*1024)} MB / {totalsize // (1024*1024)} MB)", flush=True)

    urllib.request.urlretrieve(ISO_URL, str(TARGET_ISO), reporthook=reporthook)
    print(f"[SUCCESS] Downloaded Live Bootable ISO: {TARGET_ISO} ({TARGET_ISO.stat().st_size} bytes)")
    return str(TARGET_ISO)

if __name__ == "__main__":
    download_iso()
