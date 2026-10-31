<#
.SYNOPSIS
    Boots dist/aquaos-1.0-amd64.iso in QEMU on Windows with 4GB RAM, VirtIO GPU, and Audio.
#>
param(
    [int]$MemoryMB = 4096,
    [int]$Cpus = 4
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$IsoPath = Join-Path $ProjectRoot "dist\aquaos-1.0-amd64.iso"

if (-not (Test-Path $IsoPath)) {
    Write-Error "ISO not found at $IsoPath. Run .\scripts\build-iso.ps1 first!"
}

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
    Write-Error "QEMU not found. Install QEMU (winget install SoftwareFreedomConservancy.QEMU) or boot $IsoPath in VirtualBox/VMware."
}

Write-Host "Booting AquaOS-Beta in QEMU ($MemoryMB MB RAM, $Cpus CPUs)..." -ForegroundColor Cyan
& $QemuExe `
    -m $MemoryMB `
    -smp $Cpus `
    -cdrom $IsoPath `
    -boot d `
    -vga virtio `
    -display sdl,gl=on `
    -usb -device usb-tablet
