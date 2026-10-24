# Running AquaOS in a Virtual Machine

AquaOS 1.0 Beta (Sonoma-AI Edition) is designed to run seamlessly in virtualized environments with hardware-accelerated graphics, zero-trust network filtering, and local AI computation.

---

## Option 1: Automated QEMU VM Launcher (Windows)

We provide automated launch scripts for Windows in the `scripts/` directory:

- **[`scripts/run-vm.bat`](file:///c:/Users/iamni/Desktop/AquaOS-Beta/scripts/run-vm.bat)**: Double-click to launch in one click.
- **[`scripts/run-vm.ps1`](file:///c:/Users/iamni/Desktop/AquaOS-Beta/scripts/run-vm.ps1)**: Configurable PowerShell launcher.

### Features
- **Auto-Detection**: Locates QEMU in `PATH` or standard installation directories.
- **Hardware Acceleration**: Automatically tests and activates **Windows Hypervisor Platform (WHPX)** with multi-threaded TCG fallback.
- **Pre-configured Specs**: 4 GB RAM, 4 CPU Cores, VirtIO-VGA graphics, Intel HDA sound.
- **Port Forwarding**:
  - `Host: 8765` -> `Guest: 8765` (AquaOS Live Glassmorphic Web & API)
  - `Host: 2222` -> `Guest: 22` (SSH Terminal Access)

### Usage
Run from PowerShell or Command Prompt:
```powershell
.\scripts\run-vm.ps1
```
Or with custom memory and core allocation:
```powershell
.\scripts\run-vm.ps1 -RamMB 8192 -Cores 6 -IsoPath "dist\aquaos-1.0-amd64.iso"
```

---

## Option 2: Oracle VirtualBox

To run AquaOS inside Oracle VirtualBox:

1. **Create New Machine**:
   - **Name**: `AquaOS 1.0 Beta`
   - **Type**: `Linux`
   - **Version**: `Ubuntu (64-bit)`
2. **Hardware Allocation**:
   - **Base Memory**: `4096 MB` (4 GB minimum, 8 GB recommended for local LLMs).
   - **Processors**: `4 CPUs`.
   - **Enable EFI**: Checked (Special OSes only).
3. **Display Configuration**:
   - **Video Memory**: `128 MB`.
   - **Graphics Controller**: `VMSVGA` or `VBoxSVGA`.
   - **Enable 3D Acceleration**: Checked.
4. **Storage & Boot Media**:
   - Attach `dist/aquaos-1.0-amd64.iso` to the Optical Drive.
   - Or create a 25 GB dynamic VDI disk.
5. **Start Virtual Machine**:
   - Boot into the live AquaOS desktop.
   - Log in with default live credentials:
     - **Username**: `aqua`
     - **Password**: `aqua`

---

## Option 3: VMware Workstation / Player

1. Select **File > New Virtual Machine** > **Typical (recommended)**.
2. Select **Installer disc image file (iso)** and browse to `dist/aquaos-1.0-amd64.iso` (or choose *I will install the operating system later*).
3. Select **Linux** > **Ubuntu 64-bit**.
4. Allocate at least **40 GB disk** and **4 GB RAM**.
5. Under **Display Settings**, check **Accelerate 3D graphics**.
6. Boot the VM and launch the AquaOS Wayland session.

---

## Option 4: Windows Subsystem for Linux (WSL2 + WSLg GUI)

AquaOS can also run with native Wayland GUI on Windows through WSLg:

1. Install Ubuntu 24.04 in WSL:
   ```cmd
   wsl --install -d Ubuntu
   ```
2. Clone and enter the workspace inside WSL:
   ```bash
   git clone https://github.com/iamnikhilsharma/aquaos.git ~/AquaOS-Beta
   cd ~/AquaOS-Beta
   ```
3. Install required runtime libraries:
   ```bash
   sudo apt update && sudo apt install -y labwc picom python3-gi gir1.2-gtk-4.0 firefox
   ```
4. Start the AquaOS environment:
   ```bash
   python3 scripts/preview-aquaos.py
   ```
   Open `http://localhost:8765/` in your browser, or launch the native compositor directly via `labwc -C ./aqua-desktop/session/labwc`.
