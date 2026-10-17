#  AquaOS-Beta (Sonoma-AI • Virus-Proof Edition)

**AquaOS-Beta** is an independent, virus-proof, AI-first bootable Linux distribution (built on a Debian/Ubuntu immutable SquashFS core) featuring a custom-built macOS-inspired desktop environment (**Aqua Desktop**), a **Universal Application Runtime (`aqua-universal`)**, a **Zero-Trust Security Engine (`aqua-shield`)**, and a deeply integrated **Local AI & Neural Compute Stack (`aqua-ai`)**.

---

## Key Capabilities

### 1. Aqua Intelligence (`aqua-desktop/ai/`) — Engineered for Running AI
- **AI Kernel & Memory Tuning (`98-aquaos-ai-tuning.conf`)**: Pre-tuned `vm.max_map_count=2147483642` for zero-copy `mmap` loading of massive GGUF/Safetensors weights, Transparent HugePages (`madvise`), `zram` compressed memory, and `sched_autogroup` so the desktop stays at 60+ FPS during 100% GPU/CPU inference.
- **Neural Boost Mode (`neural_boost.py`)**: One-click toggle in Control Center and AI Studio that reclaims OS pagecache, switches CPU/GPU governors to `performance`, and sets **Flash Attention (`OLLAMA_FLASH_ATTENTION=1`)** + **Q8_0 KV Cache quantization** to fit 2x longer context windows in VRAM/RAM.
- **Hardware VRAM/RAM Model Fit Estimator (`ai_engine.py`)**: Automatically inspects your GPU VRAM and system RAM to recommend models (`DeepSeek-R1`, `Qwen 2.5 Coder`, `Llama 3.2`, `Gemma 3`) and estimates tokens/sec.
- **Sandboxed AI Code Execution**: AI-generated Python and Bash scripts run inside `aqua-sandbox` (`Bubblewrap`) so autonomous AI agents can never harm your files or OS.

### 2. Virus-Proof Zero-Trust Security (`aqua-desktop/security/`)
- **Immutable Read-Only Core OS**: System directories (`/usr`, `/bin`, `/sbin`, `/lib`) are mounted read-only from a SquashFS image. Even root-level malware cannot permanently modify system binaries or survive a clean reboot.
- **Aqua Gatekeeper (`gatekeeper.py`)**: Static signature + Shannon entropy heuristic scanner that inspects ELF, Windows PE (`.exe`), macOS Mach-O (`.app`), and scripts before execution.
- **Aqua Sandbox (`sandbox.py`)**: Mandatory **Bubblewrap (`bwrap`)** container isolation that masks `~/.ssh`, `~/.gnupg`, and browser keyrings with `tmpfs` and isolates network/filesystem namespaces.
- **Kernel Lockdown & Firewall (`99-aquaos-hardening.conf` & `nftables.conf`)**: Enforces `kptr_restrict=2`, `yama.ptrace_scope=2`, and a default-deny inbound `nftables` firewall.

### 3. Universal Application Runtime (`aqua-desktop/universal/`) — "Run Anything"
- `aqua-run <file>` transparently runs:
  - **macOS Bundles (`.app`, `.dmg`)** via Darling or native AquaOS bundles
  - **Windows Apps & Games (`.exe`, `.msi`)** inside isolated Wine/Proton sandboxes
  - **Android Apps (`.apk`)** via Waydroid
  - **Portable Linux Apps (`.AppImage`, `Flatpak`)** inside Bubblewrap sandboxes
- `aqua-pkg install <pkg>` installs packages across **Debian/Ubuntu (`apt`/`.deb`)**, **Flathub (`Flatpak`)**, **Fedora (`.rpm` via Distrobox)**, and **Arch Linux (`.pkg.tar.zst`/AUR via Distrobox)**.

### 4. Aqua Desktop Environment (`aqua-desktop/`)
- **Global Top Menu Bar (`menubar/menubar.py`)**: 28px bar with Aqua system menu, active application menus, Shield status badge, AI Orb, Control Center, and clock.
- **Parabolic Magnifying Dock (`dock/dock.py`)**: Smooth cosine-squared hover zoom, pinned apps, running indicators, and Trash.
- **Spotlight (`spotlight/spotlight.py`)**: `Super+Space` launcher with fuzzy app search, scientific AST calculator, and `@ai` natural-language queries.

---

## Quick Start

### 1. Preview AquaOS Desktop Immediately (Windows / macOS / Linux)
```powershell
# Launch the interactive GUI Desktop Simulator:
python .\scripts\preview-aquaos.py

# Or run the full CLI diagnostics tour:
python .\scripts\preview-aquaos.py --cli
```

### 2. Run the Automated Verification Suite
```powershell
python -m pytest tests/ -v
```

### 3. Build the Bootable ISO (`dist/aquaos-1.0-amd64.iso`) & Boot in QEMU
```powershell
# Build the hybrid BIOS/UEFI bootable ISO via Docker or WSL2:
.\scripts\build-iso.ps1

# Boot the ISO in QEMU:
.\scripts\run-qemu.ps1
```
