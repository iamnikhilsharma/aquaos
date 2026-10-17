<#
.SYNOPSIS
    Builds the bootable AquaOS-Beta Linux ISO (dist/aquaos-1.0-amd64.iso) on Windows using Docker or WSL2.
#>
param(
    [ValidateSet("docker", "wsl")]
    [string]$Backend = "docker"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AquaOS-Beta ISO Builder (Sonoma-AI • Virus-Proof OS)    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if ($Backend -eq "docker") {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Warning "Docker CLI not found in PATH. Falling back to WSL2..."
        $Backend = "wsl"
    }
}

if ($Backend -eq "docker") {
    Write-Host "[1/2] Building ISO Builder Docker image..." -ForegroundColor Green
    docker build -t aquaos-iso-builder "$ProjectRoot\iso-builder"

    Write-Host "[2/2] Running privileged chroot/SquashFS ISO build..." -ForegroundColor Green
    docker run --rm --privileged -v "${ProjectRoot}:/workspace" aquaos-iso-builder
} else {
    Write-Host "[WSL2] Executing iso-builder/build-iso.sh inside WSL2 as root..." -ForegroundColor Green
    $WslPath = wsl wslpath -a "$ProjectRoot"
    wsl -u root bash "$WslPath/iso-builder/build-iso.sh"
}

Write-Host "`nDone! Bootable ISO output: $ProjectRoot\dist\aquaos-1.0-amd64.iso" -ForegroundColor Green
