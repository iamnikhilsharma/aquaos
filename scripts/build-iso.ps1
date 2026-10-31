<#
.SYNOPSIS
    Builds the bootable AquaOS-Beta Linux ISO (dist/aquaos-1.0-amd64.iso) on Windows using Docker or WSL2.
#>
param(
    [ValidateSet("auto", "docker", "wsl")]
    [string]$Backend = "auto"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AquaOS-Beta ISO Builder (Sonoma-AI / Virus-Proof OS)    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Detect Available Build Backend (Docker vs WSL2)
$HasDocker = $false
$HasWsl = $false

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $HasDocker = $true
}

if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    $null = wsl.exe -l -q 2>$null
    if ($LASTEXITCODE -eq 0) {
        $HasWsl = $true
    }
}

$SelectedBackend = $Backend
if ($SelectedBackend -eq "auto") {
    if ($HasDocker) {
        $SelectedBackend = "docker"
    } elseif ($HasWsl) {
        $SelectedBackend = "wsl"
    } else {
        $SelectedBackend = "none"
    }
}

if ($SelectedBackend -eq "docker" -and -not $HasDocker) {
    if ($HasWsl) {
        Write-Warning "Docker CLI not found. Automatically switching to WSL2 backend..."
        $SelectedBackend = "wsl"
    } else {
        $SelectedBackend = "none"
    }
}

if ($SelectedBackend -eq "wsl" -and -not $HasWsl) {
    if ($HasDocker) {
        Write-Warning "WSL2 distribution not found. Automatically switching to Docker backend..."
        $SelectedBackend = "docker"
    } else {
        $SelectedBackend = "none"
    }
}

# 2. If neither is available, display setup instructions
if ($SelectedBackend -eq "none") {
    Write-Host "[-] Neither Docker nor an active WSL2 Linux distribution is currently set up." -ForegroundColor Red
    Write-Host ""
    Write-Host "Building a bootable Linux ISO (SquashFS + GRUB2 + debootstrap) requires a 64-bit Linux kernel environment." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To build the ISO, please choose either Option A or Option B below:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  OPTION A: WSL2 Ubuntu (Recommended for Windows):" -ForegroundColor Green
    Write-Host "    1. Open PowerShell as Administrator" -ForegroundColor White
    Write-Host "    2. Run: wsl --install -d Ubuntu" -ForegroundColor White
    Write-Host "    3. Reboot if prompted, then re-run: .\scripts\build-iso.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "  OPTION B: Docker Desktop:" -ForegroundColor Green
    Write-Host "    1. Install Docker Desktop (e.g. winget install Docker.DockerDesktop)" -ForegroundColor White
    Write-Host "    2. Start Docker Desktop, then re-run: .\scripts\build-iso.ps1 -Backend docker" -ForegroundColor White
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    exit 1
}

# 3. Execute Build with Selected Backend
if ($SelectedBackend -eq "docker") {
    Write-Host "[1/2] Building ISO Builder Docker image..." -ForegroundColor Green
    docker build -t aquaos-iso-builder "$ProjectRoot\iso-builder"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[-] Docker image build failed." -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host "[2/2] Running privileged chroot/SquashFS ISO build..." -ForegroundColor Green
    docker run --rm --privileged -v "${ProjectRoot}:/workspace" aquaos-iso-builder
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[-] Containerized ISO build failed." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} elseif ($SelectedBackend -eq "wsl") {
    Write-Host "[WSL2] Resolving project path in WSL2..." -ForegroundColor Green
    $WslPath = (wsl.exe wslpath -a "$ProjectRoot" 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($WslPath)) {
        Write-Host "[-] Could not resolve Windows project path inside WSL2." -ForegroundColor Red
        exit 1
    }
    $WslPath = $WslPath.Trim()

    Write-Host "[WSL2] Executing iso-builder/build-iso.sh inside WSL2 as root..." -ForegroundColor Green
    wsl.exe -u root bash "$WslPath/iso-builder/build-iso.sh"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[-] WSL2 ISO build exited with error code $LASTEXITCODE." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 4. Verify Output ISO
$TargetIso = Join-Path $ProjectRoot "dist\aquaos-1.0-amd64.iso"
if (Test-Path $TargetIso) {
    $sizeMB = [math]::Round((Get-Item $TargetIso).Length / 1MB, 2)
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  SUCCESS! Bootable AquaOS ISO Created!" -ForegroundColor Green
    Write-Host "  File: $TargetIso ($sizeMB MB)" -ForegroundColor Green
    Write-Host "  Boot in QEMU: .\scripts\run-vm.ps1" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Host "[-] Build completed, but $TargetIso was not found." -ForegroundColor Red
    exit 1
}
