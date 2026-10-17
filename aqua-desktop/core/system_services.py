"""AquaOS System Services & Telemetry.

Provides hardware detection (CPU, RAM, GPU, VRAM, Disk), audio volume, display brightness,
network status, and battery telemetry for the Menu Bar, Control Center, About AquaOS, and AI Studio.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any


@dataclass
class HardwareSpecs:
    """System hardware and OS specifications."""

    os_name: str
    kernel_version: str
    hostname: str
    cpu_model: str
    cpu_cores: int
    ram_total_gb: float
    ram_available_gb: float
    gpu_model: str
    gpu_vendor: str  # "nvidia" | "amd" | "intel" | "apple" | "virtio" | "cpu"
    vram_total_gb: float
    disk_total_gb: float
    disk_free_gb: float
    immutable_root: bool


class SystemServices:
    """Interfaces with Linux hardware and system daemons with safe fallbacks."""

    def __init__(self) -> None:
        self._volume: int = 75
        self._muted: bool = False
        self._brightness: int = 85
        self._wifi_enabled: bool = True
        self._wifi_ssid: str = "AquaNet-5G"
        self._bluetooth_enabled: bool = True
        self._dnd_enabled: bool = False

    def get_hardware_specs(self) -> HardwareSpecs:
        """Detect CPU, RAM, GPU, VRAM, Disk, and Immutable RootFS status."""
        cpu_model = platform.processor() or "Generic x86_64 Processor"
        cpu_cores = os.cpu_count() or 4

        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            try:
                for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if "model name" in line:
                        cpu_model = line.split(":", 1)[1].strip()
                        break
            except OSError:
                pass

        ram_total_gb, ram_avail_gb = self._detect_memory_gb()
        gpu_model, gpu_vendor, vram_gb = self._detect_gpu()
        disk_total_gb, disk_free_gb = self._detect_disk_gb()
        immutable_root = self._check_immutable_root()

        return HardwareSpecs(
            os_name="AquaOS 1.0 Beta (Sonoma-AI)",
            kernel_version=platform.release(),
            hostname=platform.node() or "aquaos-macbook",
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            ram_total_gb=round(ram_total_gb, 2),
            ram_available_gb=round(ram_avail_gb, 2),
            gpu_model=gpu_model,
            gpu_vendor=gpu_vendor,
            vram_total_gb=round(vram_gb, 2),
            disk_total_gb=round(disk_total_gb, 1),
            disk_free_gb=round(disk_free_gb, 1),
            immutable_root=immutable_root,
        )

    @staticmethod
    def _detect_memory_gb() -> tuple[float, float]:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            try:
                total_kb = 8 * 1024 * 1024
                avail_kb = 6 * 1024 * 1024
                for line in meminfo.read_text(encoding="utf-8").splitlines():
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
                return total_kb / (1024 * 1024), avail_kb / (1024 * 1024)
            except Exception:
                pass

        # Fallback for Windows preview / non-procfs hosts
        if os.name == "nt":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                return (
                    stat.ullTotalPhys / (1024**3),
                    stat.ullAvailPhys / (1024**3),
                )
            except Exception:
                pass

        return 16.0, 12.0

    @staticmethod
    def _detect_gpu() -> tuple[str, str, float]:
        # 1. Check NVIDIA GPU via nvidia-smi
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2.0,
                ).strip()
                if out:
                    first_line = out.splitlines()[0]
                    name, mem_mb = [x.strip() for x in first_line.split(",", 1)]
                    return name, "nvidia", float(mem_mb) / 1024.0
            except Exception:
                pass

        # 2. Check Linux lspci
        if shutil.which("lspci"):
            try:
                out = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL, text=True, timeout=1.5)
                for line in out.splitlines():
                    if "VGA compatible controller" in line or "3D controller" in line:
                        desc = line.split(":", 2)[-1].strip()
                        lower = desc.lower()
                        if "nvidia" in lower:
                            return desc, "nvidia", 8.0
                        if "amd" in lower or "radeon" in lower:
                            return desc, "amd", 8.0
                        if "intel" in lower:
                            return desc, "intel", 4.0
                        return desc, "virtio", 2.0
            except Exception:
                pass

        return "Aqua Neural Graphics (Vulkan / Unified Memory)", "vulkan", 8.0

    @staticmethod
    def _detect_disk_gb() -> tuple[float, float]:
        try:
            usage = shutil.disk_usage(Path.home())
            return usage.total / (1024**3), usage.free / (1024**3)
        except Exception:
            return 256.0, 180.0

    @staticmethod
    def _check_immutable_root() -> bool:
        mounts = Path("/proc/mounts")
        if mounts.exists():
            try:
                content = mounts.read_text(encoding="utf-8")
                if "overlay / overlay" in content or "squashfs" in content:
                    return True
                for line in content.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[1] in ("/", "/usr"):
                        opts = parts[3].split(",")
                        if "ro" in opts:
                            return True
            except Exception:
                pass
        return True

    def get_volume(self) -> int:
        if shutil.which("wpctl"):
            try:
                out = subprocess.check_output(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.0,
                )
                # e.g., "Volume: 0.75"
                for tok in out.split():
                    try:
                        self._volume = int(float(tok) * 100)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        return self._volume

    def set_volume(self, percent: int) -> int:
        self._volume = max(0, min(100, int(percent)))
        if shutil.which("wpctl"):
            try:
                subprocess.run(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{self._volume}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
            except Exception:
                pass
        elif shutil.which("pactl"):
            try:
                subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{self._volume}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
            except Exception:
                pass
        return self._volume

    def get_brightness(self) -> int:
        return self._brightness

    def set_brightness(self, percent: int) -> int:
        self._brightness = max(5, min(100, int(percent)))
        if shutil.which("brightnessctl"):
            try:
                subprocess.run(
                    ["brightnessctl", "set", f"{self._brightness}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
            except Exception:
                pass
        return self._brightness

    def get_battery_status(self) -> Dict[str, Any]:
        bat_dir = Path("/sys/class/power_supply/BAT0")
        if bat_dir.exists():
            try:
                cap = int((bat_dir / "capacity").read_text().strip())
                status = (bat_dir / "status").read_text().strip()
                return {"percentage": cap, "charging": status.lower() in ("charging", "full")}
            except Exception:
                pass
        return {"percentage": 96, "charging": True}
