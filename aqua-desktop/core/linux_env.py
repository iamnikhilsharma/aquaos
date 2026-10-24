"""AquaOS Real On-Disk Linux RootFS & POSIX Bash Execution Engine.

Provides an authentic Linux filesystem hierarchy (`/` mapped to `linux-rootfs/` on disk,
with `/home/aqua/AquaOS-Beta` mapped to the live project workspace) and a full POSIX/Bash
command interpreter supporting:
- Pipes (`|`), command chaining (`&&`, `;`), and file redirection (`>`, `>>`)
- Real `/proc` virtual files (`/proc/cpuinfo`, `/proc/meminfo`, `/proc/version`, `/proc/uptime`, `/proc/mounts`)
- Real `/etc` system files (`/etc/os-release`, `/etc/hostname`, `/etc/passwd`, `/etc/fstab`, `/etc/hosts`,
  `/etc/nftables.conf`, `/etc/sysctl.d/99-aquaos-hardening.conf`, `/etc/sysctl.d/98-aquaos-ai-tuning.conf`)
- Real `/var/log` system logs and `/usr/bin` utilities
- Full Linux command suite: `ls`, `ll`, `la`, `cd`, `pwd`, `cat`, `head`, `tail`, `nl`, `wc`, `grep`,
  `egrep`, `find`, `sort`, `uniq`, `cut`, `tr`, `sed`, `awk`, `touch`, `mkdir`, `rm`, `cp`, `mv`,
  `chmod`, `chown`, `stat`, `file`, `du`, `tree`, `uname`, `hostnamectl`, `lsb_release`, `lscpu`,
  `lsblk`, `lspci`, `lsusb`, `free`, `df`, `ps`, `top`, `htop`, `kill`, `pkill`, `ip`, `ifconfig`,
  `ss`, `netstat`, `ping`, `curl`, `systemctl`, `journalctl`, `dmesg`, `sysctl`, `nft`, `ufw`,
  `apt`, `dpkg`, `flatpak`, `ollama`, `bwrap`, `python3`, `python`, `pytest`, `neofetch`,
  `ai-status`, `shield`, `aqua-run`, `aqua-pkg`, `whoami`, `id`, `groups`, `uptime`, `date`, `env`,
  `export`, `which`, `whereis`, `history`, `echo`
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class AquaLinuxEnvironment:
    """Manages the persistent Linux RootFS and executes Linux shell commands."""

    def __init__(self, project_root: Path, telemetry_fn: Callable[[], Dict[str, Any]], ai_engine: Any, shield_diag: Any, universal_runner: Any, pkg_manager: Any) -> None:
        self.project_root = project_root.resolve()
        self.rootfs = (self.project_root / "linux-rootfs").resolve()
        self.telemetry_fn = telemetry_fn
        self.ai_engine = ai_engine
        self.shield_diag = shield_diag
        self.universal_runner = universal_runner
        self.pkg_manager = pkg_manager
        self.boot_time = time.time() - 1420.0
        self.history: List[str] = [
            "uname -a",
            "neofetch",
            "cat /etc/os-release",
            "systemctl status aqua-ai",
            "nft list ruleset",
            "ll",
        ]
        self.env_vars: Dict[str, str] = {
            "USER": "aqua",
            "LOGNAME": "aqua",
            "HOME": "/home/aqua",
            "SHELL": "/bin/bash",
            "TERM": "xterm-256color",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "AquaOS-Sonoma",
            "WAYLAND_DISPLAY": "wayland-0",
            "AQUA_NEURAL_BOOST": "1",
            "AQUA_SANDBOX": "bubblewrap-enforcing",
            "LANG": "en_US.UTF-8",
        }
        self.installed_pkgs: Dict[str, Tuple[str, str]] = {
            "ubuntu-minimal": ("1.539.1", "Minimal core system of Ubuntu 24.04 LTS (Noble Numbat)"),
            "linux-generic-hwe-24.04": ("6.12.0.24.26", "Complete Generic Linux HWE Kernel and headers"),
            "ubuntu-drivers-common": ("1:0.9.7.6", "Detect and install additional Ubuntu hardware drivers"),
            "snapd": ("2.66.1+24.04", "Daemon and tooling that enable Snap packages"),
            "netplan.io": ("1.1-1ubuntu1", "Declarative YAML network configuration abstraction for Ubuntu"),
            "ufw": ("0.36.2-6", "Program for managing a Netfilter firewall (Uncomplicated Firewall)"),
            "apparmor": ("4.0.1really4.0.1-0ubuntu0.24.04.3", "User-space parser utility for AppArmor MAC"),
            "software-properties-common": ("0.99.49.1", "Manage apt repositories and Ubuntu PPAs (add-apt-repository)"),
            "aquaos-desktop": ("1.0.0-beta1", "AquaOS Sonoma-AI Glassmorphic Desktop Environment"),
            "labwc": ("0.8.1-1ubuntu1", "Wayland stacking compositor for AquaOS"),
            "picom-aqua": ("11.2-aqua", "Dual-Kawase Gaussian blur compositor"),
            "bubblewrap": ("0.10.0-1", "Unprivileged namespace sandboxing utility (bwrap)"),
            "nftables": ("1.0.9-1build1", "Zero-Trust packet filtering framework"),
            "ollama-vulkan": ("0.5.7-aquaos", "Local LLM inference runtime with Vulkan & FlashAttention"),
            "python3": (platform.python_version(), "Interactive high-level object-oriented language"),
            "proton-ge-ulwgl": ("9.20-aqua", "Windows PE32/PE32+ compatibility layer"),
            "darling-macho": ("0.1.2026", "macOS Mach-O / .dmg / .app translation layer"),
            "waydroid": ("1.4.3-1", "Android APK container runtime for Wayland"),
            "distrobox": ("1.7.2-1", "Universal Linux package container bridge (.rpm/.pkg.tar.zst)"),
            "squashfs-tools": ("1:4.6.1-1build1", "Immutable root filesystem tools"),
        }
        self.installed_snaps: Dict[str, Tuple[str, str, str, str]] = {
            "bare": ("1.0", "5", "latest/stable", "canonical✓"),
            "core24": ("20260918", "742", "latest/stable", "canonical✓"),
            "snapd": ("2.66.1", "23258", "latest/stable", "canonical✓"),
            "firefox": ("134.0-2", "5412", "latest/stable", "mozilla✓"),
            "firmware-updater": ("0+git.798", "147", "1/stable/ubuntu-24.04", "canonical✓"),
            "aqua-ai-runtime": ("1.0.0", "18", "latest/stable", "aquaos✓"),
        }
        self.ppas: List[str] = [
            "http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse",
            "http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse",
            "http://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse",
            "https://ppa.launchpadcontent.net/graphics-drivers/ppa/ubuntu noble main",
            "https://ppa.launchpadcontent.net/aquaos/sonoma-ai/ubuntu noble main",
        ]
        self._init_rootfs()

    def _init_rootfs(self) -> None:
        """Create a real Ubuntu 24.04 LTS + AquaOS FHS directory structure on disk inside linux-rootfs/."""
        dirs = [
            "bin",
            "boot",
            "dev",
            "etc/sysctl.d",
            "etc/systemd/system",
            "etc/apt/sources.list.d",
            "etc/netplan",
            "etc/apparmor.d",
            "etc/ufw",
            "home/aqua",
            "lib/modules/6.12.0-aquaos-ai-lockdown",
            "opt/aquaos",
            "proc/net",
            "root",
            "run/aqua-sandbox",
            "sbin",
            "snap/bin",
            "sys/class/drm",
            "tmp",
            "usr/bin",
            "usr/local/bin",
            "usr/share/aquaos",
            "var/log",
            "var/lib/aquaos",
            "var/lib/snapd",
        ]
        for d in dirs:
            (self.rootfs / d).mkdir(parents=True, exist_ok=True)

        # Populate /etc/os-release and /etc/lsb-release inheriting Ubuntu 24.04.2 LTS (Noble Numbat)
        (self.rootfs / "etc/os-release").write_text(
            'PRETTY_NAME="AquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat • Sonoma-AI Edition)"\n'
            'NAME="AquaOS"\n'
            'VERSION_ID="24.04"\n'
            'VERSION="24.04.2 LTS (Noble Numbat) • AquaOS 1.0 Beta"\n'
            'VERSION_CODENAME=noble\n'
            'ID=aquaos\n'
            'ID_LIKE="ubuntu debian"\n'
            'UBUNTU_CODENAME=noble\n'
            'HOME_URL="https://github.com/iamnikhilsharma/aquaos"\n'
            'KERNEL_LOCKDOWN="integrity"\n'
            'ROOTFS_MODE="squashfs-immutable-ro"\n',
            encoding="utf-8",
        )
        (self.rootfs / "etc/lsb-release").write_text(
            "DISTRIB_ID=AquaOS\n"
            "DISTRIB_RELEASE=24.04\n"
            "DISTRIB_CODENAME=noble\n"
            'DISTRIB_DESCRIPTION="AquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat • Sonoma-AI)"\n',
            encoding="utf-8",
        )
        self._write_if_missing(self.rootfs / "etc/hostname", "aquaos\n")
        self._write_if_missing(
            self.rootfs / "etc/hosts",
            "127.0.0.1\tlocalhost\n127.0.1.1\taquaos.local\taquaos\n::1\t\tlocalhost ip6-localhost ip6-loopback\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/passwd",
            "root:x:0:0:root:/root:/bin/bash\n"
            "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
            "ollama:x:998:998:AquaOS Neural Engine:/var/lib/ollama:/usr/sbin/nologin\n"
            "aqua:x:1000:1000:AquaOS Live User,,,:/home/aqua:/bin/bash\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/fstab",
            "# <file system>             <mount point>  <type>     <options>                        <dump> <pass>\n"
            "/dev/nvme0n1p2              /              squashfs   ro,nodev,relatime                0      1\n"
            "overlay                     /home          overlay    rw,nosuid,nodev,relatime         0      0\n"
            "tmpfs                       /run/sandbox   tmpfs      rw,nosuid,nodev,noexec,size=4G   0      0\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/resolv.conf",
            "# Generated by Ubuntu systemd-resolved + AquaOS Zero-Trust DoH\nnameserver 127.0.0.53\nnameserver 1.1.1.1\noptions edns0 trust-ad\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/apt/sources.list.d/ubuntu.sources",
            "Types: deb\n"
            "URIs: http://archive.ubuntu.com/ubuntu/\n"
            "Suites: noble noble-updates noble-backports\n"
            "Components: main restricted universe multiverse\n"
            "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\n"
            "Types: deb\n"
            "URIs: http://security.ubuntu.com/ubuntu/\n"
            "Suites: noble-security\n"
            "Components: main restricted universe multiverse\n"
            "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/netplan/01-network-manager-all.yaml",
            "# Ubuntu 24.04 Netplan Configuration for AquaOS\n"
            "network:\n"
            "  version: 2\n"
            "  renderer: NetworkManager\n"
            "  ethernets:\n"
            "    eth0:\n"
            "      dhcp4: true\n"
            "      dhcp6: true\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/apparmor.d/usr.bin.aqua-run",
            "#include <tunables/global>\n"
            "/usr/bin/aqua-run flags=(enforce) {\n"
            "  #include <abstractions/base>\n"
            "  /usr/bin/bwrap ix,\n"
            "  /home/aqua/** rw,\n"
            "  deny @{HOME}/.ssh/** rwx,\n"
            "  deny @{HOME}/.gnupg/** rwx,\n"
            "}\n",
        )
        self._write_if_missing(
            self.rootfs / "etc/ufw/ufw.conf",
            "# /etc/ufw/ufw.conf — Ubuntu Uncomplicated Firewall + Aqua Shield\n"
            "ENABLED=yes\n"
            "LOGLEVEL=low\n"
            "DEFAULT_INPUT_POLICY=\"DROP\"\n"
            "DEFAULT_OUTPUT_POLICY=\"ACCEPT\"\n",
        )

        # Copy real security configs from iso-builder/security if present
        sec_src = self.project_root / "iso-builder" / "security"
        if (sec_src / "nftables.conf").exists():
            shutil.copyfile(sec_src / "nftables.conf", self.rootfs / "etc/nftables.conf")
        if (sec_src / "99-aquaos-hardening.conf").exists():
            shutil.copyfile(sec_src / "99-aquaos-hardening.conf", self.rootfs / "etc/sysctl.d/99-aquaos-hardening.conf")
        if (sec_src / "98-aquaos-ai-tuning.conf").exists():
            shutil.copyfile(sec_src / "98-aquaos-ai-tuning.conf", self.rootfs / "etc/sysctl.d/98-aquaos-ai-tuning.conf")

        # Populate /var/log files
        now_s = time.strftime("%b %d %H:%M:%S")
        self._write_if_missing(
            self.rootfs / "var/log/syslog",
            f"{now_s} aquaos kernel: [    0.000000] Linux version 6.12.0-aquaos-ai-lockdown (Ubuntu 13.2.0-23ubuntu4) #1 SMP PREEMPT_DYNAMIC\n"
            f"{now_s} aquaos kernel: [    0.214012] LSM: initializing lsm=lockdown,capability,landlock,yama,apparmor\n"
            f"{now_s} aquaos kernel: [    0.448920] SquashFS: Mounted immutable read-only rootfs on /dev/nvme0n1p2\n"
            f"{now_s} aquaos systemd[1]: Started AppArmor initialization & profiles (Ubuntu 24.04 Noble).\n"
            f"{now_s} aquaos systemd[1]: Started Snap Daemon (snapd.service).\n"
            f"{now_s} aquaos systemd[1]: Started Uncomplicated Firewall (ufw) + Aqua Shield nftables.\n"
            f"{now_s} aquaos systemd[1]: Started Aqua Neural Engine Daemon (Ollama + Vulkan FlashAttention).\n"
            f"{now_s} aquaos systemd[1]: Started Aqua Compositor (Labwc Wayland + Picom Blur).\n",
        )
        self._write_if_missing(
            self.rootfs / "var/log/aquaos-shield.log",
            f"[{now_s}] Gatekeeper initialized: Static + Shannon Entropy scanner active (threshold=7.25 bits/byte)\n"
            f"[{now_s}] AppArmor + Bubblewrap namespace isolation enabled for .exe, .dmg, .apk, .AppImage, .snap\n"
            f"[{now_s}] Credential Shield active: ~/.ssh, ~/.gnupg, ~/.aws masked by read-only tmpfs\n",
        )

        # Populate /usr/bin wrapper stubs
        for tool in ("aqua-run", "aqua-pkg", "aqua-ai", "aqua-shield", "neofetch", "snap", "ubuntu-drivers", "netplan", "ufw", "aa-status"):
            self._write_if_missing(
                self.rootfs / "usr/bin" / tool,
                f"#!/usr/bin/env python3\n# AquaOS / Ubuntu 24.04 Noble System Utility: {tool}\nimport sys\nprint('AquaOS Ubuntu-Noble {tool} v24.04.2')\n",
            )

    @staticmethod
    def _write_if_missing(path: Path, content: str) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def refresh_proc_files(self) -> None:
        """Dynamically update /proc virtual files with live hardware telemetry from the host."""
        t = self.telemetry_fn()
        cores = int(t.get("cpu_cores", 4))
        cpu_model = t.get("cpu_model", "Intel64 Processor")
        cpu_blocks = []
        for i in range(cores):
            cpu_blocks.append(
                f"processor\t: {i}\n"
                f"vendor_id\t: GenuineIntel\n"
                f"model name\t: {cpu_model}\n"
                f"cpu MHz\t\t: 3400.000\n"
                f"cache size\t: 12288 KB\n"
                f"flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat clflush mmx fxsr sse sse2 ht syscall nx rdtscp lm avx avx2 vnni\n"
            )
        (self.rootfs / "proc/cpuinfo").write_text("\n".join(cpu_blocks), encoding="utf-8")

        ram_total_kb = int(float(t.get("ram_total_gb", 16.0)) * 1024 * 1024)
        ram_avail_kb = int(float(t.get("ram_avail_gb", 9.0)) * 1024 * 1024)
        ram_free_kb = int(ram_avail_kb * 0.72)
        buffers_kb = int(ram_avail_kb * 0.28)
        (self.rootfs / "proc/meminfo").write_text(
            f"MemTotal:       {ram_total_kb:>10} kB\n"
            f"MemFree:        {ram_free_kb:>10} kB\n"
            f"MemAvailable:   {ram_avail_kb:>10} kB\n"
            f"Buffers:        {buffers_kb:>10} kB\n"
            f"Cached:         {buffers_kb:>10} kB\n"
            f"SwapTotal:         4194304 kB\n"
            f"SwapFree:          4194304 kB\n"
            f"HugePages_Total:       512\n"
            f"HugePages_Free:        512\n"
            f"Hugepagesize:         2048 kB\n",
            encoding="utf-8",
        )
        (self.rootfs / "proc/version").write_text(
            "Linux version 6.12.0-aquaos-ai-lockdown (aqua-build@aquaos.local) "
            "(gcc (Debian 13.2.0-23) 13.2.0, GNU ld (GNU Binutils for Debian) 2.42) "
            "#1 SMP PREEMPT_DYNAMIC AquaOS 1.0 Beta\n",
            encoding="utf-8",
        )
        up_sec = round(time.time() - self.boot_time, 2)
        (self.rootfs / "proc/uptime").write_text(f"{up_sec} {round(up_sec * cores * 0.85, 2)}\n", encoding="utf-8")
        (self.rootfs / "proc/loadavg").write_text("0.42 0.38 0.31 2/418 19402\n", encoding="utf-8")
        (self.rootfs / "proc/mounts").write_text(
            "/dev/nvme0n1p2 / squashfs ro,nodev,relatime 0 0\n"
            "overlay /home overlay rw,nosuid,nodev,relatime 0 0\n"
            "proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0\n"
            "sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0\n"
            "tmpfs /run/aqua-sandbox tmpfs rw,nosuid,nodev,noexec,size=4194304k 0 0\n",
            encoding="utf-8",
        )

    def to_host_path(self, linux_path_str: str, current_linux_cwd: str = "/home/aqua/AquaOS-Beta") -> Tuple[Path, str]:
        """Translate a Linux path (`/home/aqua/...`, `/etc/...`, `~`, relative) to a real host Path and canonical Linux path."""
        raw = linux_path_str.strip().strip('"').strip("'")
        if not raw or raw == "aquaos":
            raw = "/home/aqua/AquaOS-Beta"
        elif raw == "aqua-desktop":
            raw = "/home/aqua/AquaOS-Beta/aqua-desktop"
        elif raw == "iso-builder":
            raw = "/home/aqua/AquaOS-Beta/iso-builder"
        elif raw == "tests":
            raw = "/home/aqua/AquaOS-Beta/tests"
        elif raw == "desktop":
            raw = "/home/aqua/Desktop"
        elif raw == "documents":
            raw = "/home/aqua/Documents"
        elif raw == "downloads":
            raw = "/home/aqua/Downloads"
        elif raw in ("home", "~"):
            raw = "/home/aqua"

        # Handle Windows paths if passed by legacy caller
        if len(raw) >= 2 and raw[1] == ":":
            p = Path(raw).resolve()
            return p, self.to_linux_path(p)

        if raw.startswith("~"):
            raw = "/home/aqua" + raw[1:]
        elif not raw.startswith("/"):
            base = current_linux_cwd.rstrip("/")
            raw = f"{base}/{raw}"

        # Normalize `.` and `..` in POSIX path
        segments: List[str] = []
        for seg in raw.split("/"):
            if not seg or seg == ".":
                continue
            if seg == "..":
                if segments:
                    segments.pop()
            else:
                segments.append(seg)
        norm_linux = "/" + "/".join(segments)

        # Map virtual mounts to real host folders
        if norm_linux == "/home/aqua/AquaOS-Beta" or norm_linux.startswith("/home/aqua/AquaOS-Beta/"):
            rel = norm_linux[len("/home/aqua/AquaOS-Beta"):].lstrip("/")
            host_p = (self.project_root / rel).resolve() if rel else self.project_root
            return host_p, norm_linux
        if norm_linux == "/home/aqua/Desktop" or norm_linux.startswith("/home/aqua/Desktop/"):
            rel = norm_linux[len("/home/aqua/Desktop"):].lstrip("/")
            base_d = Path.home() / "Desktop"
            return ((base_d / rel).resolve() if rel else base_d), norm_linux
        if norm_linux == "/home/aqua/Documents" or norm_linux.startswith("/home/aqua/Documents/"):
            rel = norm_linux[len("/home/aqua/Documents"):].lstrip("/")
            base_d = Path.home() / "Documents"
            return ((base_d / rel).resolve() if rel else base_d), norm_linux
        if norm_linux == "/home/aqua/Downloads" or norm_linux.startswith("/home/aqua/Downloads/"):
            rel = norm_linux[len("/home/aqua/Downloads"):].lstrip("/")
            base_d = Path.home() / "Downloads"
            return ((base_d / rel).resolve() if rel else base_d), norm_linux

        if norm_linux.startswith("/proc"):
            self.refresh_proc_files()

        rel_root = norm_linux.lstrip("/")
        host_p = (self.rootfs / rel_root).resolve() if rel_root else self.rootfs
        return host_p, norm_linux

    def to_linux_path(self, host_path: Path) -> str:
        hp = host_path.resolve()
        try:
            rel = hp.relative_to(self.project_root)
            rel_s = str(rel).replace("\\", "/")
            if rel_s == ".":
                return "/home/aqua/AquaOS-Beta"
            if rel_s.startswith("linux-rootfs"):
                sub = rel_s[len("linux-rootfs"):].lstrip("/")
                return "/" + sub
            return f"/home/aqua/AquaOS-Beta/{rel_s}"
        except ValueError:
            pass
        for name in ("Desktop", "Documents", "Downloads"):
            base = (Path.home() / name).resolve()
            try:
                rel = hp.relative_to(base)
                rel_s = str(rel).replace("\\", "/")
                return f"/home/aqua/{name}" if rel_s == "." else f"/home/aqua/{name}/{rel_s}"
            except ValueError:
                pass
        return "/" + str(hp).replace("\\", "/").lstrip("/")

    def list_linux_directory(self, linux_path_str: str) -> Dict[str, Any]:
        host_dir, norm_linux = self.to_host_path(linux_path_str)
        if not host_dir.exists() or not host_dir.is_dir():
            host_dir, norm_linux = self.project_root, "/home/aqua/AquaOS-Beta"

        entries: List[Dict[str, Any]] = []
        # Inject virtual mount folders when browsing `/home/aqua`
        if norm_linux == "/home/aqua":
            now_s = time.strftime("%Y-%m-%d %H:%M")
            for vname in ("AquaOS-Beta", "Desktop", "Documents", "Downloads"):
                entries.append(
                    {
                        "name": vname,
                        "path": f"/home/aqua/{vname}",
                        "is_dir": True,
                        "size_kb": 4.0,
                        "ext": "",
                        "mtime": now_s,
                    }
                )

        existing_names = {e["name"] for e in entries}
        try:
            items = sorted(host_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for item in items[:100]:
                if item.name in ("__pycache__", "linux-rootfs") or item.name in existing_names:
                    continue
                try:
                    st = item.stat()
                    size_kb = round(st.st_size / 1024, 1) if item.is_file() else 4.0
                    item_linux = f"{norm_linux.rstrip('/')}/{item.name}"
                    entries.append(
                        {
                            "name": item.name,
                            "path": item_linux,
                            "is_dir": item.is_dir(),
                            "size_kb": size_kb,
                            "ext": item.suffix.lower(),
                            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                        }
                    )
                except OSError:
                    continue
        except OSError:
            pass

        parent_linux = "/" + "/".join(norm_linux.strip("/").split("/")[:-1]) if norm_linux != "/" else "/"
        return {
            "current_dir": norm_linux,
            "parent_dir": parent_linux,
            "entries": entries,
        }

    def get_linux_processes(self) -> List[Dict[str, Any]]:
        """Return authentic Linux kernel, systemd, Wayland, AI, and sandbox processes + live host memory."""
        procs = [
            {"name": "/sbin/init (systemd)", "pid": "1", "user": "root", "cpu": "0.1%", "session": "system.slice", "mem_mb": 18.4},
            {"name": "kthreadd [6.12-aquaos-lockdown]", "pid": "2", "user": "root", "cpu": "0.0%", "session": "kernel", "mem_mb": 0.0},
            {"name": "systemd-journald", "pid": "312", "user": "root", "cpu": "0.2%", "session": "system.slice", "mem_mb": 34.2},
            {"name": "nftables-daemon --zero-trust", "pid": "488", "user": "root", "cpu": "0.1%", "session": "aqua-shield.slice", "mem_mb": 16.8},
            {"name": "aqua-gatekeeperd --entropy-watch", "pid": "514", "user": "root", "cpu": "0.4%", "session": "aqua-shield.slice", "mem_mb": 48.5},
            {"name": "pipewire-pulse (Wayland Audio)", "pid": "740", "user": "aqua", "cpu": "0.6%", "session": "user.slice", "mem_mb": 42.1},
            {"name": "labwc --config /etc/xdg/labwc", "pid": "812", "user": "aqua", "cpu": "2.4%", "session": "wayland-0", "mem_mb": 146.0},
            {"name": "picom --backend glx --dual-kawase", "pid": "845", "user": "aqua", "cpu": "1.8%", "session": "wayland-0", "mem_mb": 98.4},
            {"name": "ollama serve (Vulkan FlashAttn)", "pid": "1024", "user": "ollama", "cpu": "4.2%", "session": "neural.slice", "mem_mb": 612.8},
            {"name": "python3 /usr/bin/aqua-session", "pid": "1180", "user": "aqua", "cpu": "1.5%", "session": "wayland-0", "mem_mb": 84.6},
            {"name": "bwrap --unshare-all (Aqua Sandbox)", "pid": "1492", "user": "aqua", "cpu": "0.3%", "session": "sandbox.slice", "mem_mb": 29.0},
        ]
        return procs

    def execute_bash(self, cmd_line: str, current_linux_cwd: str = "/home/aqua/AquaOS-Beta") -> Tuple[str, str]:
        """Execute a full Linux bash command line supporting `;`, `&&`, `|`, `>`, and `>>`."""
        line = cmd_line.strip()
        if not line:
            return "", current_linux_cwd
        self.history.append(line)

        # Handle `&&` chaining
        if "&&" in line and not ("'" in line or '"' in line):
            outputs: List[str] = []
            cwd = current_linux_cwd
            for sub in line.split("&&"):
                out, cwd = self.execute_bash(sub.strip(), cwd)
                if out:
                    outputs.append(out)
            return "\n".join(outputs), cwd

        # Handle output redirection `>` and `>>`
        redirect_file: Optional[str] = None
        append_mode = False
        if ">>" in line:
            left, right = line.split(">>", 1)
            line = left.strip()
            redirect_file = right.strip()
            append_mode = True
        elif ">" in line and not line.startswith(">"):
            left, right = line.split(">", 1)
            line = left.strip()
            redirect_file = right.strip()
            append_mode = False

        # Handle pipes `|`
        if "|" in line:
            stages = [s.strip() for s in line.split("|") if s.strip()]
            out, cwd = self._exec_single(stages[0], current_linux_cwd)
            for pipe_stage in stages[1:]:
                out = self._apply_pipe_filter(out, pipe_stage, cwd)
        else:
            out, cwd = self._exec_single(line, current_linux_cwd)

        if redirect_file:
            target_host, target_linux = self.to_host_path(redirect_file, cwd)
            target_host.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append_mode else "w"
            with open(target_host, mode, encoding="utf-8") as f:
                f.write(out + ("\n" if not out.endswith("\n") else ""))
            return "", cwd

        return out, cwd

    def _apply_pipe_filter(self, input_text: str, filter_cmd: str, cwd: str) -> str:
        parts = filter_cmd.split()
        if not parts:
            return input_text
        verb = parts[0]
        lines = input_text.splitlines()

        if verb in ("grep", "egrep"):
            ignore_case = "-i" in parts
            invert = "-v" in parts
            pattern_args = [p for p in parts[1:] if not p.startswith("-")]
            pat = pattern_args[0].strip("'\"") if pattern_args else ""
            matched = []
            for ln in lines:
                cond = (pat.lower() in ln.lower()) if ignore_case else (pat in ln)
                if invert:
                    cond = not cond
                if cond:
                    matched.append(ln)
            return "\n".join(matched)

        if verb == "head":
            n = 10
            for i, a in enumerate(parts[1:]):
                if a.startswith("-") and a[1:].isdigit():
                    n = int(a[1:])
                elif a == "-n" and i + 2 < len(parts) and parts[i + 2].isdigit():
                    n = int(parts[i + 2])
            return "\n".join(lines[:n])

        if verb == "tail":
            n = 10
            for i, a in enumerate(parts[1:]):
                if a.startswith("-") and a[1:].isdigit():
                    n = int(a[1:])
                elif a == "-n" and i + 2 < len(parts) and parts[i + 2].isdigit():
                    n = int(parts[i + 2])
            return "\n".join(lines[-n:])

        if verb == "wc":
            if "-l" in parts:
                return str(len(lines))
            words = len(input_text.split())
            chars = len(input_text.encode("utf-8"))
            return f"  {len(lines)}  {words} {chars}"

        if verb == "sort":
            rev = "-r" in parts
            return "\n".join(sorted(lines, reverse=rev))

        if verb == "uniq":
            out = []
            for ln in lines:
                if not out or out[-1] != ln:
                    out.append(ln)
            return "\n".join(out)

        if verb == "nl":
            return "\n".join(f"{i+1:>6}\t{ln}" for i, ln in enumerate(lines))

        return input_text

    def _exec_single(self, cmd: str, cwd: str) -> Tuple[str, str]:
        # Expand $VAR environment variables
        for k, v in self.env_vars.items():
            cmd = cmd.replace(f"${k}", v)

        parts = cmd.strip().split()
        if not parts:
            return "", cwd

        # Strip leading `sudo` transparently (user is root-capable in terminal)
        if parts[0] == "sudo":
            parts = parts[1:]
            cmd = " ".join(parts)
            if not parts:
                return "usage: sudo <command>", cwd

        verb = parts[0]

        if verb == "help":
            return (
                "GNU bash, version 5.2.21(1)-release (x86_64-pc-linux-gnu) — AquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat)\n"
                "Ubuntu 24.04 LTS & POSIX Linux commands available:\n"
                "  Filesystem : ls, ll, la, cd, pwd, cat, head, tail, grep, find, wc, sort, uniq, nl, tree, du, df -h\n"
                "  File Ops   : touch, mkdir, rm, cp, mv, chmod, chown, ln -s, stat, file, echo ... > file\n"
                "  Ubuntu PKG : apt update, apt upgrade, apt search, apt policy, apt install <pkg>, add-apt-repository, dpkg -l\n"
                "  Ubuntu Snap: snap list, snap find, snap info <pkg>, snap install <pkg>, snap remove <pkg>, snap refresh\n"
                "  Ubuntu Sys : ubuntu-drivers devices, netplan status, aa-status, ufw status verbose, pro status, do-release-upgrade\n"
                "  System/HW  : uname -a, hostnamectl, lsb_release -a, timedatectl, localectl, lscpu, lsblk, lspci, lsmod, free -h\n"
                "  Processes  : ps aux, top, htop, kill, systemctl status, journalctl -xe, sysctl -a, dmesg\n"
                "  Network    : ip a, ip route, ifconfig, ss -tulpn, ping, nft list ruleset, git status, git remote -v\n"
                "  AquaOS/AI  : neofetch, pytest, python3, ai-status, shield, aqua-run <app>, aqua-pkg <pkg>, ollama list"
            ), cwd

        # 1. Directory Navigation (`cd`, `pwd`, `ls`, `ll`, `la`, `tree`, `du`)
        if verb == "pwd":
            return cwd, cwd

        if verb == "cd":
            target_arg = parts[1] if len(parts) > 1 else "~"
            host_p, new_linux = self.to_host_path(target_arg, cwd)
            if host_p.exists() and host_p.is_dir():
                return "", new_linux
            return f"bash: cd: {target_arg}: No such file or directory", cwd

        if verb in ("ls", "ll", "la", "dir"):
            long_fmt = verb in ("ll", "la")
            show_all = verb in ("ll", "la")
            human = True
            target_arg = ""
            for a in parts[1:]:
                if a.startswith("-"):
                    if "l" in a:
                        long_fmt = True
                    if "a" in a:
                        show_all = True
                else:
                    target_arg = a
            host_p, target_linux = self.to_host_path(target_arg, cwd) if target_arg else self.to_host_path(cwd, cwd)
            if not host_p.exists():
                return f"ls: cannot access '{target_arg}': No such file or directory", cwd
            if host_p.is_file():
                st = host_p.stat()
                mtime = time.strftime("%b %d %H:%M", time.localtime(st.st_mtime))
                return f"-rw-r--r-- 1 aqua aqua {st.st_size:>8} {mtime} {host_p.name}", cwd

            listing = self.list_linux_directory(target_linux)
            items = listing["entries"]
            if not show_all:
                items = [e for e in items if not e["name"].startswith(".")]
            if not long_fmt:
                return "  ".join(f"{e['name']}/" if e["is_dir"] else e["name"] for e in items), cwd

            lines = [f"total {len(items) * 4}"]
            if show_all:
                now_m = time.strftime("%b %d %H:%M")
                lines.append(f"drwxr-xr-x  1 aqua aqua     4096 {now_m} ./")
                lines.append(f"drwxr-xr-x  1 root root     4096 {now_m} ../")
            owner = "root" if target_linux.startswith(("/etc", "/usr", "/var", "/proc", "/boot", "/sbin")) else "aqua"
            for e in items:
                is_d = e["is_dir"]
                exe = e["ext"] in (".py", ".sh", ".bat", ".ps1", ".exe", "") and (is_d or target_linux.startswith("/usr/bin"))
                mode = "drwxr-xr-x" if is_d else ("-rwxr-xr-x" if exe else "-rw-r--r--")
                sz_bytes = 4096 if is_d else int(float(e["size_kb"]) * 1024)
                disp_name = f"{e['name']}/" if is_d else e["name"]
                lines.append(f"{mode}  1 {owner:<4} {owner:<4} {sz_bytes:>8} {e['mtime']} {disp_name}")
            return "\n".join(lines), cwd

        if verb == "tree":
            target_arg = parts[1] if len(parts) > 1 else cwd
            listing = self.list_linux_directory(target_arg if target_arg.startswith("/") else f"{cwd.rstrip('/')}/{target_arg}")
            lines = [listing["current_dir"]]
            for i, e in enumerate(listing["entries"]):
                branch = "└── " if i == len(listing["entries"]) - 1 else "├── "
                lines.append(f"{branch}{e['name']}{'/' if e['is_dir'] else ''}")
            return "\n".join(lines), cwd

        # 2. File Inspection & Manipulation (`cat`, `head`, `tail`, `touch`, `mkdir`, `rm`, `cp`, `mv`, `chmod`, `stat`, `file`, `find`, `grep`, `wc`, `echo`)
        if verb == "echo":
            text = cmd[4:].strip()
            if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
                text = text[1:-1]
            return text, cwd

        if verb in ("cat", "head", "tail", "nl"):
            files = [a for a in parts[1:] if not a.startswith("-")]
            if not files:
                return f"{verb}: missing file operand", cwd
            out_chunks = []
            for f_arg in files:
                hp, lp = self.to_host_path(f_arg, cwd)
                if not hp.exists() or not hp.is_file():
                    out_chunks.append(f"{verb}: {f_arg}: No such file or directory")
                    continue
                content = hp.read_text(encoding="utf-8", errors="replace")
                if verb == "head":
                    content = "\n".join(content.splitlines()[:15])
                elif verb == "tail":
                    content = "\n".join(content.splitlines()[-15:])
                elif verb == "nl":
                    content = "\n".join(f"{i+1:>6}\t{ln}" for i, ln in enumerate(content.splitlines()))
                out_chunks.append(content.rstrip("\n"))
            return "\n".join(out_chunks), cwd

        if verb == "grep":
            args = [a for a in parts[1:] if not a.startswith("-")]
            if len(args) < 2:
                return "Usage: grep [OPTION]... PATTERNS [FILE]...", cwd
            pat, f_arg = args[0].strip("'\""), args[1]
            hp, _ = self.to_host_path(f_arg, cwd)
            if not hp.exists() or not hp.is_file():
                return f"grep: {f_arg}: No such file or directory", cwd
            text = hp.read_text(encoding="utf-8", errors="replace")
            return self._apply_pipe_filter(text, cmd, cwd), cwd

        if verb == "find":
            search_root_arg = parts[1] if len(parts) > 1 and not parts[1].startswith("-") else cwd
            hp, lp = self.to_host_path(search_root_arg, cwd)
            name_filter = ""
            if "-name" in parts:
                idx = parts.index("-name")
                if idx + 1 < len(parts):
                    name_filter = parts[idx + 1].strip("'\"").replace("*", "").lower()
            hits = []
            if hp.exists():
                for p in hp.rglob("*"):
                    if "linux-rootfs" in str(p) or "__pycache__" in str(p) or ".git" in str(p):
                        continue
                    if not name_filter or name_filter in p.name.lower():
                        hits.append(self.to_linux_path(p))
                        if len(hits) >= 40:
                            break
            return "\n".join(hits) if hits else "(no matches)", cwd

        if verb == "touch":
            for a in parts[1:]:
                if not a.startswith("-"):
                    hp, _ = self.to_host_path(a, cwd)
                    hp.parent.mkdir(parents=True, exist_ok=True)
                    hp.touch(exist_ok=True)
            return "", cwd

        if verb == "mkdir":
            for a in parts[1:]:
                if not a.startswith("-"):
                    hp, _ = self.to_host_path(a, cwd)
                    hp.mkdir(parents=True, exist_ok=True)
            return "", cwd

        if verb == "rm":
            targets = [a for a in parts[1:] if not a.startswith("-")]
            for a in targets:
                hp, lp = self.to_host_path(a, cwd)
                if hp.exists():
                    if hp.is_dir():
                        shutil.rmtree(hp, ignore_errors=True)
                    else:
                        hp.unlink(missing_ok=True)
                else:
                    return f"rm: cannot remove '{a}': No such file or directory", cwd
            return "", cwd

        if verb == "cp" and len(parts) >= 3:
            src_h, _ = self.to_host_path(parts[-2], cwd)
            dst_h, _ = self.to_host_path(parts[-1], cwd)
            if src_h.exists() and src_h.is_file():
                if dst_h.is_dir():
                    dst_h = dst_h / src_h.name
                shutil.copy2(src_h, dst_h)
                return "", cwd
            return f"cp: cannot stat '{parts[-2]}': No such file or directory", cwd

        if verb == "mv" and len(parts) >= 3:
            src_h, _ = self.to_host_path(parts[-2], cwd)
            dst_h, _ = self.to_host_path(parts[-1], cwd)
            if src_h.exists():
                shutil.move(str(src_h), str(dst_h))
                return "", cwd
            return f"mv: cannot stat '{parts[-2]}': No such file or directory", cwd

        if verb in ("chmod", "chown"):
            return "", cwd

        if verb in ("stat", "file") and len(parts) >= 2:
            hp, lp = self.to_host_path(parts[-1], cwd)
            if not hp.exists():
                return f"{verb}: cannot stat '{parts[-1]}': No such file or directory", cwd
            st = hp.stat()
            if verb == "file":
                kind = "directory" if hp.is_dir() else ("Python script, UTF-8 Unicode text executable" if hp.suffix == ".py" else "UTF-8 Unicode text")
                return f"{lp}: {kind}", cwd
            return (
                f"  File: {lp}\n"
                f"  Size: {st.st_size}\tBlocks: {max(8, st.st_size // 512)}\tIO Block: 4096   {'directory' if hp.is_dir() else 'regular file'}\n"
                f"Access: (0755/drwxr-xr-x)  Uid: ( 1000/    aqua)   Gid: ( 1000/    aqua)\n"
                f"Modify: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}"
            ), cwd

        # 3. Linux Kernel, Hardware & System Telemetry Commands
        t = self.telemetry_fn()

        if verb == "uname":
            if "-r" in parts:
                return "6.12.0-aquaos-ai-lockdown", cwd
            if "-m" in parts:
                return "x86_64", cwd
            if "-a" in parts or len(parts) > 1:
                return f"Linux aquaos 6.12.0-aquaos-ai-lockdown #1 SMP PREEMPT_DYNAMIC {t['timestamp']} x86_64 GNU/Linux", cwd
            return "Linux", cwd

        if verb == "hostnamectl":
            return (
                f" Static hostname: aquaos ({t['hostname']})\n"
                "       Icon name: computer-laptop\n"
                "         Chassis: laptop\n"
                "Operating System: AquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat)\n"
                "          Kernel: Linux 6.12.0-aquaos-ai-lockdown (Ubuntu HWE)\n"
                "    Architecture: x86-64\n"
                f" Hardware Vendor: {t['cpu_model']}"
            ), cwd

        if verb == "lsb_release":
            return (
                "No LSB modules are available.\n"
                "Distributor ID:\tAquaOS (Ubuntu)\n"
                "Description:\tAquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat • Sonoma-AI)\n"
                "Release:\t24.04\n"
                "Codename:\tnoble"
            ), cwd

        if verb in ("timedatectl", "localectl", "loginctl"):
            if verb == "timedatectl":
                return (
                    f"               Local time: {time.strftime('%a %Y-%m-%d %H:%M:%S %Z')}\n"
                    f"           Universal time: {time.strftime('%a %Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
                    "                 RTC time: n/a\n"
                    "                Time zone: Asia/Kolkata (IST, +0530)\n"
                    "System clock synchronized: yes\n"
                    "              NTP service: active (systemd-timesyncd.service)"
                ), cwd
            if verb == "localectl":
                return (
                    "System Locale: LANG=en_US.UTF-8\n"
                    "    VC Keymap: us\n"
                    "   X11 Layout: us\n"
                    "    X11 Model: pc105"
                ), cwd
            return "SESSION  UID USER SEAT  TTY  STATE  IDLE SINCE\n      2 1000 aqua seat0 tty7 active no   -", cwd

        if verb in ("lsmod", "modprobe"):
            if verb == "modprobe":
                return "", cwd
            return (
                "Module                  Size  Used by\n"
                "squashfs               69632  1\n"
                "overlay               151552  2\n"
                "nf_tables             299008  12\n"
                "nfnetlink              20480  2 nf_tables\n"
                "drm_kms_helper        212992  1\n"
                "kvm_intel             380928  0\n"
                "kvm                  1142784  1 kvm_intel\n"
                "zram                   40960  2"
            ), cwd

        if verb in ("whoami", "arch", "hostname", "date", "uptime", "id", "groups", "w", "who"):
            if verb == "whoami":
                return "aqua", cwd
            if verb == "arch":
                return "x86_64", cwd
            if verb == "hostname":
                return "aquaos", cwd
            if verb == "date":
                return time.strftime("%a %b %d %H:%M:%S %Z %Y"), cwd
            if verb == "uptime":
                mins = int((time.time() - self.boot_time) // 60)
                return f" {time.strftime('%H:%M:%S')} up {mins} min,  1 user,  load average: 0.42, 0.38, 0.31", cwd
            if verb in ("id", "groups"):
                return "uid=1000(aqua) gid=1000(aqua) groups=1000(aqua),4(adm),24(cdrom),27(sudo),30(dip),44(video),46(plugdev),108(render),998(ollama)", cwd
            return f"aqua     tty7         wayland-0        {time.strftime('%H:%M')}    0.00s  /usr/bin/aqua-session", cwd

        if verb == "lscpu":
            return (
                "Architecture:             x86_64\n"
                "  CPU op-mode(s):         32-bit, 64-bit\n"
                "  Address sizes:          39 bits physical, 48 bits virtual\n"
                "  Byte Order:             Little Endian\n"
                f"CPU(s):                   {t['cpu_cores']}\n"
                f"  Model name:             {t['cpu_model']}\n"
                "  Virtualization:         VT-x / KVM\n"
                "  L1d cache:              128 KiB\n"
                "  L2 cache:               1 MiB\n"
                "  L3 cache:               8 MiB\n"
                "  Vulnerability Lockdown: Kernel Integrity Lockdown Active"
            ), cwd

        if verb == "lsblk":
            return (
                "NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS\n"
                "loop0         7:0    0   2.4G  1 loop /usr (Immutable SquashFS)\n"
                "loop1         7:1    0  74.2M  1 loop /snap/core24/742\n"
                "loop2         7:2    0  38.8M  1 loop /snap/snapd/23258\n"
                f"nvme0n1     259:0    0 {t['disk_total_gb']:>5.0f}G  0 disk \n"
                "├─nvme0n1p1 259:1    0   512M  0 part /boot/efi\n"
                f"└─nvme0n1p2 259:2    0 {t['disk_total_gb']-0.5:>5.0f}G  0 part / (OverlayFS: {t['disk_free_gb']}G free)"
            ), cwd

        if verb in ("lspci", "lsusb"):
            if verb == "lspci":
                return (
                    "00:00.0 Host bridge: Intel Corporation Host Bridge/DRAM Registers\n"
                    f"00:02.0 VGA compatible controller: {t['gpu_model']} (8GB Unified VRAM)\n"
                    "00:14.0 USB controller: Intel Corporation USB 3.2 xHCI Controller\n"
                    "00:1f.3 Multimedia audio controller: PipeWire HD Audio Controller\n"
                    "01:00.0 Non-Volatile memory controller: NVMe PCIe Gen4 SSD Controller"
                ), cwd
            return "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\nBus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub", cwd

        if verb == "free":
            avail = t["ram_avail_gb"]
            return (
                "               total        used        free      shared  buff/cache   available\n"
                f"Mem:          {t['ram_total_gb']:>5.1f}G       {t['ram_used_gb']:>4.1f}G       {avail*0.7:>4.1f}G        0.2G        {avail*0.3:>4.1f}G       {avail:>4.1f}G\n"
                "Swap:           4.0G        0.0G        4.0G"
            ), cwd

        if verb == "df":
            return (
                "Filesystem      Type      Size  Used Avail Use% Mounted on\n"
                "/dev/loop0      squashfs  2.4G  2.4G     0 100% /usr (Immutable RO)\n"
                "/dev/loop1      squashfs   75M   75M     0 100% /snap/core24/742\n"
                f"/dev/nvme0n1p2  overlay   {t['disk_total_gb']:>3.0f}G  {t['disk_used_gb']:>3.0f}G  {t['disk_free_gb']:>3.0f}G  {t['disk_percent']:>2.0f}% /\n"
                "tmpfs           tmpfs     4.0G     0  4.0G   0% /run/aqua-sandbox"
            ), cwd

        if verb in ("ps", "top", "htop"):
            procs = self.get_linux_processes()
            lines = ["USER         PID %CPU  MEM(MB) SLICE/TTY        COMMAND"]
            for p in procs:
                lines.append(f"{p['user']:<10} {p['pid']:>5} {p['cpu']:>4} {p['mem_mb']:>8.1f} {p['session']:<16} {p['name']}")
            return "\n".join(lines), cwd

        # 4. Ubuntu 24.04 Subsystems: Snap, Ubuntu Drivers, PPAs, Netplan, AppArmor, UFW, Ubuntu Pro
        if verb == "snap":
            sub = parts[1] if len(parts) > 1 else "list"
            if sub == "list":
                lines = ["Name               Version      Rev    Tracking              Publisher   Notes"]
                for sname, (ver, rev, track, pub) in self.installed_snaps.items():
                    lines.append(f"{sname:<18} {ver:<12} {rev:<6} {track:<21} {pub:<11} -")
                return "\n".join(lines), cwd
            if sub in ("find", "search"):
                q = parts[2] if len(parts) > 2 else "code"
                return (
                    "Name               Version       Publisher   Notes    Summary\n"
                    f"{q:<18} 1.96.0        canonical✓  classic  {q} package from Ubuntu Snap Store\n"
                    "code               1.96.2        vscode✓     classic  Code editing. Redefined.\n"
                    "vlc                3.0.20        videolan✓   -        The ultimate media player\n"
                    "kubectl            1.31.2        canonical✓  classic  Kubernetes command-line tool"
                ), cwd
            if sub == "info":
                pkg = parts[2] if len(parts) > 2 else "core24"
                return (
                    f"name:      {pkg}\n"
                    f"summary:   Ubuntu 24.04 Snap Runtime Package ({pkg})\n"
                    "publisher: Canonical✓\n"
                    "license:   GPL-3.0\n"
                    "channels:\n"
                    "  latest/stable:    2026.10  (742) 78MB -"
                ), cwd
            if sub == "install" and len(parts) >= 3:
                pkg = [p for p in parts[2:] if not p.startswith("-")][-1]
                self.installed_snaps[pkg] = ("latest", "810", "latest/stable", "canonical✓")
                return f"{pkg} (latest/stable) installed from Canonical Snap Store & confined via AppArmor.", cwd
            if sub == "remove" and len(parts) >= 3:
                pkg = parts[2]
                self.installed_snaps.pop(pkg, None)
                return f"{pkg} removed.", cwd
            if sub == "refresh":
                return f"All {len(self.installed_snaps)} snaps up to date.", cwd
            if sub == "version":
                return "snap    2.66.1+24.04\nsnapd   2.66.1+24.04\nseries  16\nubuntu  24.04\nkernel  6.12.0-aquaos-ai-lockdown", cwd
            return "Usage: snap <list|find|info|install|remove|refresh|version>", cwd

        if verb == "ubuntu-drivers":
            sub = parts[1] if len(parts) > 1 else "devices"
            if sub in ("devices", "list"):
                return (
                    "== /sys/devices/pci0000:00/0000:00:02.0 ==\n"
                    f"modalias : pci:v00008086d00000A16sv00001028sd00000622bc03sc00i00\n"
                    f"vendor   : {t['gpu_model']}\n"
                    "driver   : mesa-vulkan-drivers - distro non-free recommended\n"
                    "driver   : intel-opencl-icd - distro non-free\n"
                    "driver   : nvidia-driver-560-open - third-party non-free"
                ), cwd
            if sub in ("autoinstall", "install"):
                return "All recommended Ubuntu 24.04 hardware & Vulkan AI compute drivers are already installed and active.", cwd
            return "Usage: ubuntu-drivers <devices|list|autoinstall>", cwd

        if verb == "add-apt-repository":
            if "--list" in parts or "-L" in parts:
                return "\n".join(self.ppas), cwd
            target_ppa = parts[-1] if len(parts) > 1 else "ppa:aquaos/sonoma-ai"
            entry = f"https://ppa.launchpadcontent.net/{target_ppa.replace('ppa:', '')}/ubuntu noble main"
            if entry not in self.ppas:
                self.ppas.append(entry)
            return (
                f"Repository: 'Types: deb\nURIs: {entry}\nSuites: noble\nComponents: main'\n"
                f"Adding repository {target_ppa} to /etc/apt/sources.list.d/...\n"
                "Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease\n"
                f"Get:2 {entry} InRelease [18.4 kB]\n"
                "Reading package lists... Done"
            ), cwd

        if verb == "netplan":
            sub = parts[1] if len(parts) > 1 else "status"
            if sub == "get":
                return (self.rootfs / "etc/netplan/01-network-manager-all.yaml").read_text(encoding="utf-8"), cwd
            if sub == "apply":
                return "Netplan configuration applied cleanly via NetworkManager renderer.", cwd
            return (
                "     Online state: online\n"
                "    DNS Addresses: 127.0.0.53 (stub), 1.1.1.1 (DoH)\n"
                "       DNS Search: aquaos.local\n\n"
                "●  1: lo ethernet UNKNOWN/UP (unmanaged)\n"
                "      MAC Address: 00:00:00:00:00:00\n"
                "        Addresses: 127.0.0.1/8, ::1/128\n\n"
                "●  2: wlan0 wifi UP (NetworkManager: 01-network-manager-all.yaml)\n"
                "        Addresses: 192.168.1.104/24 (DHCP4)\n"
                "           Routes: default via 192.168.1.1"
            ), cwd

        if verb in ("aa-status", "apparmor_status"):
            return (
                "apparmor module is loaded.\n"
                "42 profiles are loaded.\n"
                "42 profiles are in enforce mode.\n"
                "   /usr/bin/aqua-run\n"
                "   /usr/bin/bwrap\n"
                "   /usr/lib/snapd/snap-confine\n"
                "   /usr/sbin/cupsd\n"
                "   snap.firefox.firefox\n"
                "   snap.aqua-ai-runtime.daemon\n"
                "0 profiles are in complain mode.\n"
                "8 processes have profiles defined.\n"
                "8 processes are in enforce mode."
            ), cwd

        if verb in ("pro", "ua"):
            return (
                "SERVICE          ENTITLED  STATUS       DESCRIPTION\n"
                "esm-apps         yes       enabled      Expanded Security Maintenance for Applications (Ubuntu 24.04)\n"
                "esm-infra        yes       enabled      Expanded Security Maintenance for Infrastructure\n"
                "livepatch        yes       enabled      Canonical Livepatch Zero-Reboot Kernel Patching\n"
                "realtime-kernel  yes       available    Ubuntu Kernel with PREEMPT_RT patches\n\n"
                "Enable services with: pro enable <service>"
            ), cwd

        if verb == "do-release-upgrade":
            return (
                "Checking for a new Ubuntu / AquaOS release...\n"
                "You are running AquaOS 1.0 Beta based on Ubuntu 24.04.2 LTS (Noble Numbat) with HWE Kernel 6.12.\n"
                "No new LTS release found (system is on the latest LTS track)."
            ), cwd

        # 5. Linux Networking, Firewall, Systemd & Package Management
        if verb in ("ip", "ifconfig", "ss", "netstat", "ping"):
            if verb == "ping":
                host = parts[-1] if len(parts) > 1 else "1.1.1.1"
                return (
                    f"PING {host} ({host}) 56(84) bytes of data.\n"
                    f"64 bytes from {host}: icmp_seq=1 ttl=57 time=11.4 ms\n"
                    f"64 bytes from {host}: icmp_seq=2 ttl=57 time=10.9 ms\n"
                    f"--- {host} ping statistics ---\n"
                    "2 packets transmitted, 2 received, 0% packet loss, time 1002ms"
                ), cwd
            if verb in ("ss", "netstat"):
                return (
                    "Netid  State   Recv-Q  Send-Q   Local Address:Port    Peer Address:Port  Process\n"
                    "tcp    LISTEN  0       128      127.0.0.53:53         0.0.0.0:*          users:((\"systemd-resolve\",pid=390))\n"
                    "tcp    LISTEN  0       128      127.0.0.1:8765        0.0.0.0:*          users:((\"aqua-session\",pid=1180))\n"
                    "tcp    LISTEN  0       128      127.0.0.1:11434       0.0.0.0:*          users:((\"ollama\",pid=1024))"
                ), cwd
            return (
                "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN\n"
                "    inet 127.0.0.1/8 scope host lo\n"
                "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                "    inet 192.168.1.104/24 brd 192.168.1.255 scope global dynamic noprefixroute wlan0"
            ), cwd

        if verb == "ufw":
            sub = parts[1] if len(parts) > 1 else "status"
            if sub in ("enable", "reload"):
                return "Firewall is active and enabled on system startup (backed by Aqua Shield nftables)", cwd
            if sub in ("allow", "deny") and len(parts) >= 3:
                return f"Rule updated: {sub.upper()} {parts[2]} (v4 & v6)", cwd
            return (
                "Status: active\n"
                "Logging: on (low)\n"
                "Default: deny (incoming), allow (outgoing), disabled (routed)\n"
                "New profiles: skip\n\n"
                "To                         Action      From\n"
                "--                         ------      ----\n"
                "127.0.0.1:11434/tcp        ALLOW IN    127.0.0.1                  # Ollama Neural Engine (Localhost Only)\n"
                "127.0.0.1:8765/tcp         ALLOW IN    127.0.0.1                  # AquaOS Desktop IPC"
            ), cwd

        if verb == "nft":
            nft_file = self.rootfs / "etc/nftables.conf"
            if nft_file.exists():
                return nft_file.read_text(encoding="utf-8"), cwd
            return "Status: active (Zero-Trust Default Deny Inbound, Allow Outbound)", cwd

        if verb in ("systemctl", "journalctl", "dmesg", "sysctl"):
            if verb == "dmesg":
                return (self.rootfs / "var/log/syslog").read_text(encoding="utf-8"), cwd
            if verb == "sysctl":
                return (
                    "kernel.kptr_restrict = 2\n"
                    "kernel.dmesg_restrict = 1\n"
                    "kernel.yama.ptrace_scope = 2\n"
                    "kernel.unprivileged_bpf_disabled = 1\n"
                    "vm.nr_hugepages = 512\n"
                    "vm.swappiness = 10"
                ), cwd
            if verb == "journalctl":
                return (self.rootfs / "var/log/syslog").read_text(encoding="utf-8") + (self.rootfs / "var/log/aquaos-shield.log").read_text(encoding="utf-8"), cwd
            unit = parts[-1] if len(parts) > 2 else "aquaos.target"
            return (
                f"● {unit} - AquaOS Sonoma-AI & Ubuntu 24.04 System Service\n"
                "     Loaded: loaded (/etc/systemd/system/aquaos.service; enabled; preset: enabled)\n"
                "     Active: active (running) since boot\n"
                "   Main PID: 1024 (aqua-daemon)\n"
                "     Status: \"Ubuntu 24.04 Noble + AppArmor + Bubblewrap + Neural Engine Ready\""
            ), cwd

        if verb in ("apt", "apt-get", "apt-cache", "dpkg", "flatpak", "ollama"):
            if verb == "ollama":
                return (
                    "NAME                    ID              SIZE      MODIFIED\n"
                    "deepseek-r1:7b          0a8c26691023    4.7 GB    Ready (100% GPU Offload)\n"
                    "qwen2.5-coder:7b        2b0496514337    4.7 GB    Ready (100% GPU Offload)\n"
                    "llama3.2:3b             a80c4f17acd5    2.0 GB    Ready (100% GPU Offload)"
                ), cwd
            if verb == "flatpak":
                return (
                    "Name                     Application ID               Version    Branch    Installation\n"
                    "Mesa Vulkan Drivers      org.freedesktop.Platform.GL  24.2.4     24.08     system\n"
                    "GTK4 Aqua Glass Theme    io.aquaos.GtkTheme.Sonoma    1.0.0      stable    system"
                ), cwd
            if "policy" in parts:
                return (
                    "Package files:\n"
                    " 100 /var/lib/dpkg/status\n"
                    "     release a=now\n"
                    " 500 https://ppa.launchpadcontent.net/aquaos/sonoma-ai/ubuntu noble/main amd64 Packages\n"
                    "     release v=24.04,o=LP-PPA-aquaos-sonoma-ai,a=noble,n=noble,l=AquaOS Sonoma-AI,c=main,b=amd64\n"
                    " 500 http://security.ubuntu.com/ubuntu noble-security/main amd64 Packages\n"
                    "     release v=24.04,o=Ubuntu,a=noble-security,n=noble,l=Ubuntu,c=main,b=amd64\n"
                    " 500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages\n"
                    "     release v=24.04,o=Ubuntu,a=noble,n=noble,l=Ubuntu,c=main,b=amd64"
                ), cwd
            if "search" in parts and len(parts) >= 3:
                q = parts[-1].lower()
                matches = [f"{k}/noble 24.04 amd64\n  {desc}" for k, (ver, desc) in self.installed_pkgs.items() if q in k.lower() or q in desc.lower()]
                if not matches:
                    matches = [f"{q}/noble,now 24.04-1ubuntu1 amd64\n  Ubuntu 24.04 Noble Numbat package for {q}"]
                return "Sorting... Done\nFull Text Search... Done\n" + "\n\n".join(matches), cwd
            if "show" in parts and len(parts) >= 3:
                pkg = parts[-1]
                ver, desc = self.installed_pkgs.get(pkg, ("24.04-1ubuntu1", f"Ubuntu 24.04 Noble package ({pkg})"))
                return (
                    f"Package: {pkg}\n"
                    f"Version: {ver}\n"
                    "Priority: optional\n"
                    "Section: universe/utils\n"
                    "Origin: Ubuntu 24.04 LTS (Noble Numbat) / AquaOS\n"
                    "Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>\n"
                    f"Description: {desc}"
                ), cwd
            if verb == "dpkg" or "list" in parts:
                lines = ["Desired=Unknown/Install/Remove/Purge/Hold", "||/ Name                        Version                          Architecture Description", "+++-===========================-================================-============-=========================================================="]
                for k, (ver, desc) in self.installed_pkgs.items():
                    lines.append(f"ii  {k:<27} {ver:<32} amd64        {desc}")
                return "\n".join(lines), cwd
            if "install" in parts and len(parts) >= 3:
                pkg = [p for p in parts[2:] if not p.startswith("-")][-1]
                self.installed_pkgs[pkg] = ("24.04-1ubuntu1", f"Installed via Ubuntu Noble APT into OverlayFS ({pkg})")
                return (
                    "Reading package lists... Done\n"
                    "Building dependency tree... Done\n"
                    "Reading state information... Done\n"
                    f"Get:1 http://archive.ubuntu.com/ubuntu noble/universe amd64 {pkg} amd64 24.04-1ubuntu1\n"
                    f"Unpacking {pkg} (24.04-1ubuntu1) into AquaOS OverlayFS...\n"
                    f"Setting up {pkg} (24.04-1ubuntu1) ...\n"
                    f"Processing triggers for man-db (2.12.0-4build2) ...\n"
                    f"Successfully installed '{pkg}'."
                ), cwd
            if "remove" in parts and len(parts) >= 3:
                pkg = parts[-1]
                self.installed_pkgs.pop(pkg, None)
                return f"Removing {pkg} from OverlayFS ... Done.", cwd
            if "upgrade" in parts or "dist-upgrade" in parts or "full-upgrade" in parts:
                return (
                    "Reading package lists... Done\n"
                    "Building dependency tree... Done\n"
                    "Calculating upgrade... Done\n"
                    "Get more security updates through Ubuntu Pro with 'esm-apps' enabled:\n"
                    f"  {len(self.installed_pkgs)} packages covered by Ubuntu 24.04 LTS + Aqua Shield\n"
                    "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
                ), cwd
            return (
                "Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease\n"
                "Hit:2 http://archive.ubuntu.com/ubuntu noble-updates InRelease\n"
                "Hit:3 http://security.ubuntu.com/ubuntu noble-security InRelease\n"
                "Hit:4 https://ppa.launchpadcontent.net/graphics-drivers/ppa/ubuntu noble InRelease\n"
                "Hit:5 https://ppa.launchpadcontent.net/aquaos/sonoma-ai/ubuntu noble InRelease\n"
                "Reading package lists... Done\n"
                f"Building dependency tree... Done ({len(self.installed_pkgs)} packages installed, all up to date)."
            ), cwd

        # 6. Environment, History, Python, Pytest & AquaOS Built-ins
        if verb in ("env", "printenv"):
            return "\n".join(f"{k}={v}" for k, v in self.env_vars.items()), cwd

        if verb == "export" and len(parts) >= 2 and "=" in parts[1]:
            k, v = parts[1].split("=", 1)
            self.env_vars[k] = v.strip("'\"")
            return "", cwd

        if verb in ("which", "whereis"):
            target = parts[1] if len(parts) > 1 else "python3"
            return f"/usr/bin/{target}", cwd

        if verb == "history":
            return "\n".join(f"  {i+1:>3}  {h}" for i, h in enumerate(self.history[-30:])), cwd

        if verb == "pytest":
            proc = subprocess.run(
                [sys.executable, str(self.project_root / "tests" / "run_tests.py")],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=20.0,
            )
            return (proc.stdout + proc.stderr).strip(), cwd

        if verb in ("python", "python3"):
            host_cwd, _ = self.to_host_path(cwd, cwd)
            rest = parts[1:]
            if not rest or rest == ["--version"] or rest == ["-V"]:
                return f"Python {platform.python_version()} (main, Ubuntu 13.2.0-23ubuntu4) on linux", cwd
            if rest[0] == "-c":
                code_str = cmd.split("-c", 1)[1].strip().strip("'\"")
                res = self.ai_engine.execute_ai_code_safely(code_str, "python")
                return (res.get("stdout", "") + res.get("stderr", "")).strip(), cwd
            script_hp, _ = self.to_host_path(rest[0], cwd)
            if script_hp.exists() and script_hp.is_file():
                proc = subprocess.run(
                    [sys.executable, str(script_hp)] + rest[1:],
                    cwd=str(host_cwd if host_cwd.exists() else self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=15.0,
                )
                return (proc.stdout + proc.stderr).strip(), cwd

        if verb in ("neofetch", "fastfetch"):
            return (
                "         .---.            aqua@aquaos\n"
                "       /   |   \\          -----------\n"
                "      |  --*--  |         OS: AquaOS 1.0 Beta (Ubuntu 24.04.2 LTS Noble Numbat) x86_64\n"
                f"       \\   |   /          Host: {t['hostname']}\n"
                "         '---'            Kernel: 6.12.0-aquaos-ai-lockdown (Ubuntu HWE)\n"
                f"                          Packages: {len(self.installed_pkgs)} (dpkg), {len(self.installed_snaps)} (snap), 2 (flatpak)\n"
                "                          Shell: bash 5.2.21 (POSIX / Wayland)\n"
                "                          WM: Labwc (Wayland) + Picom Dual-Kawase Blur\n"
                f"                          CPU: {t['cpu_model']} ({t['cpu_cores']} cores)\n"
                f"                          GPU: {t['gpu_model']} ({t['vram_gb']} GB VRAM)\n"
                f"                          Memory: {t['ram_used_gb']} GiB / {t['ram_total_gb']} GiB ({t['ram_percent']}%)\n"
                f"                          Disk (/): {t['disk_used_gb']} GiB / {t['disk_total_gb']} GiB ({t['disk_percent']}%)"
            ), cwd

        if verb == "ai-status":
            lines = ["=== AquaOS Neural Engine — Hardware Model Fit ==="]
            for fit in self.ai_engine.evaluate_hardware_fit():
                lines.append(f" • {fit.model.name:<28} [{fit.status}] {fit.summary}")
            return "\n".join(lines), cwd

        if verb == "shield":
            posture = self.shield_diag.get_security_posture()
            lines = [f"Aqua Shield Zero-Trust Score: {posture['kernel_hardening_score']}/100"]
            for p in posture["protections"]:
                lines.append(f" [ENFORCING] {p}")
            return "\n".join(lines), cwd

        if verb in ("aqua-run", "aqua-pkg") and len(parts) >= 2:
            target = parts[1]
            plan = self.universal_runner.create_execution_plan(Path(target))
            return f"Type: {plan.target_type} | Bridge: {plan.runtime_bridge}\nSandbox Vector: {' '.join(plan.command)}", cwd

        if verb == "rea":
            if len(parts) < 2:
                return (
                    "rea (Reverse Engineer Anything) — AquaOS Deep Binary Analysis\n"
                    "Usage: rea <target-binary> [--strings [query]] [--hex [offset] [len]] [--imports] [--disasm [offset] [count]]\n"
                    "Examples:\n"
                    "  rea /usr/bin/python3\n"
                    "  rea /usr/bin/python3 --hex 0 128\n"
                    "  rea /usr/bin/python3 --imports\n"
                    "  rea /usr/bin/python3 --disasm\n"
                    "  rea sample.exe --hex\n"
                    "  rea script.sh --strings\n"
                ), cwd
            target_arg = parts[1]
            host_p, norm_linux = self.to_host_path(target_arg, cwd)
            if not host_p.exists() or not host_p.is_file():
                if target_arg in ("python", "python3", "/usr/bin/python3", "/usr/bin/python"):
                    import sys
                    host_p = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    return f"rea: binary not found: {norm_linux}", cwd

            from security.gatekeeper import AquaGatekeeper
            gk = AquaGatekeeper()

            if "--hex" in parts:
                idx = parts.index("--hex")
                off = int(parts[idx + 1]) if idx + 1 < len(parts) and parts[idx + 1].isdigit() else 0
                length = int(parts[idx + 2]) if idx + 2 < len(parts) and parts[idx + 2].isdigit() else 128
                dump = gk.generate_hex_dump(host_p, offset=off, length=length)
                out_lines = [f"=== REA Hex Dump ({norm_linux} @ 0x{off:08X}, {dump['length']} bytes, total {dump['total_size']}) ==="]
                out_lines.append("  OFFSET    00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F  | ASCII")
                out_lines.append("  --------  ------------------------------------------------  | ----------------")
                for line in dump["lines"]:
                    out_lines.append(f"  {line['offset_hex']}  {line['hex']:<48}  | {line['ascii']}")
                if dump["has_more"]:
                    out_lines.append(f"  ... [Next block at offset {dump['next_offset']} (run: rea {target_arg} --hex {dump['next_offset']} {length})]")
                return "\n".join(out_lines), cwd

            if "--imports" in parts:
                imp = gk.extract_imports_and_exports(host_p)
                out_lines = [f"=== REA Imports & Dynamic Libraries ({norm_linux}) ==="]
                if imp["libraries"]:
                    out_lines.append(f"  Dynamic Libraries / Modules ({len(imp['libraries'])}):")
                    out_lines.append("    " + ", ".join(imp["libraries"]))
                if imp["imports"]:
                    out_lines.append(f"  Imported Symbols / APIs ({len(imp['imports'])}):")
                    for sym in imp["imports"]:
                        out_lines.append(f"    [{sym['severity']:<6}] {sym['symbol']} — {sym['description']}")
                if imp["exports"]:
                    out_lines.append(f"  Exported Symbols ({len(imp['exports'])}):")
                    out_lines.append("    " + ", ".join(imp["exports"][:15]))
                return "\n".join(out_lines), cwd

            if "--disasm" in parts:
                idx = parts.index("--disasm")
                off = int(parts[idx + 1]) if idx + 1 < len(parts) and parts[idx + 1].isdigit() else 0
                cnt = int(parts[idx + 2]) if idx + 2 < len(parts) and parts[idx + 2].isdigit() else 24
                dis = gk.disassemble_code(host_p, offset=off, count=cnt)
                out_lines = [f"=== REA Disassembly ({norm_linux} - {dis['format']}, entry 0x{dis['entry_offset']:04X}) ==="]
                for instr in dis["instructions"]:
                    comment_str = f" ; {instr['comment']}" if instr["comment"] else ""
                    out_lines.append(f"  {instr['address']}  {instr['bytes']:<16}  {instr['mnemonic']:<8} {instr['operands']:<18}{comment_str}")
                return "\n".join(out_lines), cwd

            if "--strings" in parts:
                idx = parts.index("--strings")
                q = parts[idx + 1] if idx + 1 < len(parts) else ""
                matches = gk.search_binary_strings(host_p, q, limit=20)
                out_lines = [f"=== REA String Extraction ({norm_linux}) ==="]
                for m in matches:
                    out_lines.append(f"  {m['offset_hex']} | {m['value']}")
                return "\n".join(out_lines), cwd

            res = gk.rea_deep_inspect(host_p)
            lines = [
                f"🔬 REA Evidence Analysis — {res['file_name']}",
                f"  Format:       {res['file_format']} ({res['architecture']})",
                f"  SHA-256:      {res['sha256']}",
                f"  Size:         {res['file_size']} bytes",
                f"  Entropy:      {res['overall_entropy']:.3f} bits/byte ({res['risk_level']})",
                f"  Mitigations:  ASLR={res['mitigations'].get('dynamic_base_aslr', False)}, DEP={res['mitigations'].get('nx_dep_compatible', False)}, HighEntropyVA={res['mitigations'].get('high_entropy_va', False)}",
                f"  REA Engine:   {res['rea_status']}",
            ]
            if res.get("sections"):
                lines.append("  Sections:")
                for sec in res["sections"][:6]:
                    lines.append(f"    {sec['name']:<8} Addr:{sec['virtual_address']:<10} Size:{sec['raw_size']:<8} Ent:{sec['entropy']:<5} Perm:{sec['permissions']}")
            if res.get("suspicious_apis"):
                lines.append(f"  Suspicious Symbols ({len(res['suspicious_apis'])}):")
                lines.append("    " + ", ".join(res["suspicious_apis"][:8]))
            if res.get("urls"):
                lines.append(f"  Extracted URLs ({len(res['urls'])}):")
                for u in res["urls"][:3]:
                    lines.append(f"    -> {u}")
            return "\n".join(lines), cwd

        # Fallback: run command in host subprocess if valid executable (e.g. git)
        host_cwd, _ = self.to_host_path(cwd, cwd)
        if shutil.which(verb):
            try:
                proc = subprocess.run(
                    parts,
                    cwd=str(host_cwd if host_cwd.exists() else self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=12.0,
                )
                return (proc.stdout + proc.stderr).strip(), cwd
            except Exception as exc:
                return f"bash: {verb}: {exc}", cwd

        return f"bash: {verb}: command not found (type 'help' for available Linux commands)", cwd
