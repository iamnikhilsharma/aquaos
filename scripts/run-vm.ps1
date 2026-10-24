<#
.SYNOPSIS
    AquaOS 1.0 Beta Virtual Machine Runner for Windows (scripts/run-vm.ps1)
    Launches AquaOS inside QEMU with hardware acceleration, port forwarding, and automatic setup.

.DESCRIPTION
    Features:
    - Auto-detects QEMU installation (in PATH or Program Files)
    - Automatically enables Windows Hypervisor Platform (WHPX) acceleration with TCG fallback
    - Configures 4GB RAM, 4 CPU Cores, VirtIO network and display
    - Forwards ports: 8765 (AquaOS Desktop & UI) and 2222 (SSH terminal)
    - Boots from dist/aquaos-1.0-amd64.iso or creates a fast QEMU virtual disk
#>

param(
    [string]$IsoPath = "dist\aquaos-1.0-amd64.iso",
    [string]$DiskPath = "dist\aquaos-disk.qcow2",
    [int]$RamMB = 4096,
    [int]$Cores = 4,
    [switch]$NoGui,
    [switch]$ForceInstall,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   AquaOS 1.0 Beta -- Virtual Machine Launcher (QEMU on Windows)   " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Locate QEMU executable
$QemuExe = $null
$PossiblePaths = @(
    "qemu-system-x86_64",
    "C:\Program Files\qemu\qemu-system-x86_64.exe",
    "C:\Program Files (x86)\qemu\qemu-system-x86_64.exe",
    "$env:LOCALAPPDATA\Programs\qemu\qemu-system-x86_64.exe"
)

foreach ($p in $PossiblePaths) {
    if (Get-Command $p -ErrorAction SilentlyContinue) {
        $QemuExe = (Get-Command $p).Source
        break
    }
    if (Test-Path $p) {
        $QemuExe = $p
        break
    }
}

if (-not $QemuExe) {
    Write-Host '[!] QEMU not found in PATH or standard install directories.' -ForegroundColor Yellow
    Write-Host '[*] Attempting automatic installation via scripts/setup_qemu_user.py...' -ForegroundColor Green
    try {
        python (Join-Path $ProjectRoot "scripts\setup_qemu_user.py")
        foreach ($p in $PossiblePaths) {
            if (Test-Path $p) { $QemuExe = $p; break }
        }
    } catch {
        Write-Host "[-] Auto-install failed: $_" -ForegroundColor Red
    }
}

if (-not $QemuExe -or (-not (Test-Path $QemuExe))) {
    Write-Host '[!] Could not locate qemu-system-x86_64.exe.' -ForegroundColor Red
    Write-Host '    Please download and install QEMU from: https://www.qemu.org/download/#windows' -ForegroundColor White
    exit 1
}

Write-Host ('[+] QEMU Engine Found: {0}' -f $QemuExe) -ForegroundColor Green

# 2. Check Acceleration (WHPX vs TCG)
$Accel = "tcg"
try {
    # Check if Windows Hypervisor Platform is active
    $testProc = Start-Process -FilePath $QemuExe -ArgumentList "-accel whpx -version" -NoNewWindow -PassThru -Wait -ErrorAction SilentlyContinue
    if ($testProc.ExitCode -eq 0) {
        $Accel = "whpx,accel=tcg"
        Write-Host '[+] Hardware Acceleration: Windows Hypervisor Platform (WHPX) Enabled' -ForegroundColor Green
    } else {
        Write-Host '[*] Hypervisor WHPX unavailable. Using multi-threaded TCG CPU emulation.' -ForegroundColor Yellow
    }
} catch {
    $Accel = "tcg"
}

# 3. Ensure Dist Directory Exists
$DistDir = Join-Path $ProjectRoot "dist"
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}

$FullIsoPath = Join-Path $ProjectRoot $IsoPath
$FullDiskPath = Join-Path $ProjectRoot $DiskPath

# 4. Check for boot media
$BootArgs = @()
$QemuImgExe = Join-Path (Split-Path $QemuExe) "qemu-img.exe"

if (Test-Path $FullIsoPath) {
    Write-Host ('[+] Booting from Live ISO: {0}' -f $FullIsoPath) -ForegroundColor Green
    $BootArgs += @("-cdrom", $FullIsoPath, "-boot", "d")
} else {
    Write-Host ('[*] No prebuilt ISO found at {0}.' -f $IsoPath) -ForegroundColor Yellow
    Write-Host ('[*] Setting up AquaOS fast virtual disk ({0})...' -f $DiskPath) -ForegroundColor White
    
    if ((-not (Test-Path $FullDiskPath)) -and (Test-Path $QemuImgExe)) {
        & $QemuImgExe create -f qcow2 $FullDiskPath 20G | Out-Null
        Write-Host ('[+] Created 20GB QCOW2 Virtual Disk: {0}' -f $FullDiskPath) -ForegroundColor Green
    }
    
    if (Test-Path $FullDiskPath) {
        $BootArgs += @("-drive", "file=$FullDiskPath,format=qcow2,if=virtio")
    }
}

# 5. Assemble Full QEMU Command Line
$QemuArgs = @(
    "-name", "AquaOS 1.0 Beta (Sonoma-AI Linux)",
    "-machine", "q35",
    "-accel", $Accel,
    "-m", "${RamMB}M",
    "-smp", "$Cores",
    "-cpu", "max",
    "-device", "intel-hda",
    "-device", "hda-duplex",
    "-device", "virtio-net-pci,netdev=net0",
    "-netdev", "user,id=net0,hostfwd=tcp::8765-:8765,hostfwd=tcp::2222-:22"
)

if ($NoGui) {
    $QemuArgs += @("-display", "none")
} else {
    $QemuArgs += @("-vga", "virtio", "-display", "default,show-cursor=on")
}

$QemuArgs += $BootArgs

Write-Host "------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "VM Configuration:" -ForegroundColor White
Write-Host "  RAM:           $RamMB MB" -ForegroundColor White
Write-Host "  CPU Cores:     $Cores" -ForegroundColor White
Write-Host "  Port Forwards: Host 8765 -> Guest 8765 (AquaOS Web / API)" -ForegroundColor Cyan
Write-Host "                 Host 2222 -> Guest 22 (SSH)" -ForegroundColor Cyan
Write-Host "------------------------------------------------------------------" -ForegroundColor DarkGray

if ($DryRun) {
    Write-Host '[DRY RUN] QEMU Command Line:' -ForegroundColor Yellow
    $argString = [string]::Join(' ', $QemuArgs)
    Write-Host ($QemuExe + ' ' + $argString) -ForegroundColor Cyan
    return
}

Write-Host '[*] Starting AquaOS Virtual Machine...' -ForegroundColor Green

& $QemuExe @QemuArgs
