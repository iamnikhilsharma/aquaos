<#
.SYNOPSIS
    Automated Setup & Build Pipeline for AquaOS 1.0 Beta ISO
    Elevates to Administrator, enables WHPX acceleration, installs Ubuntu WSL2,
    and triggers the full ISO build and QEMU test.
#>

param(
    [switch]$SkipVmBoot
)

$ErrorActionPreference = "Continue"

# 1. Check for Administrator Privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[*] Requesting Administrator elevation (UAC prompt)..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    $argList = @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptPath`"")
    if ($SkipVmBoot) { $argList += "-SkipVmBoot" }
    
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    Write-Host "[+] Elevated installer launched. Please click 'Yes' on the Windows UAC prompt." -ForegroundColor Green
    return
}

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   AquaOS 1.0 Beta -- Automated ISO Build Pipeline (Elevated)     " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Project Directory: $ProjectRoot" -ForegroundColor DarkGray
Write-Host ""

# 2. Enable Windows Hypervisor Platform (WHPX) for QEMU Hardware Acceleration
Write-Host "[1/4] Checking Windows Hypervisor Platform (WHPX)..." -ForegroundColor Yellow
try {
    $whpxFeature = Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -ErrorAction SilentlyContinue
    if ($whpxFeature -and $whpxFeature.State -ne "Enabled") {
        Write-Host "      Enabling HypervisorPlatform feature for hardware acceleration..." -ForegroundColor Cyan
        Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -NoRestart -ErrorAction SilentlyContinue | Out-Null
        Write-Host "      [+] Windows Hypervisor Platform Enabled!" -ForegroundColor Green
    } else {
        Write-Host "      [+] Windows Hypervisor Platform is already configured." -ForegroundColor Green
    }
} catch {
    Write-Host "      [*] Hypervisor check skipped: $_" -ForegroundColor DarkGray
}

# 3. Install WSL2 and Ubuntu Distribution
Write-Host "`n[2/4] Setting up WSL2 Ubuntu Linux environment..." -ForegroundColor Yellow
$hasWslDistro = $false
try {
    $distros = wsl.exe -l -q 2>$null
    if ($LASTEXITCODE -eq 0 -and ($distros -join "").Trim().Length -gt 0) {
        $hasWslDistro = $true
        Write-Host "      [+] Existing WSL2 Linux distribution detected: $($distros -join ', ')" -ForegroundColor Green
    }
} catch {}

if (-not $hasWslDistro) {
    Write-Host "      [*] Installing WSL2 and Ubuntu (this downloads the official Ubuntu environment)..." -ForegroundColor Cyan
    wsl.exe --install -d Ubuntu --web-download
    if ($LASTEXITCODE -ne 0) {
        # Fallback to standard install
        wsl.exe --install -d Ubuntu
    }
}

# Verify WSL
$wslOk = $false
try {
    $null = wsl.exe -l -q 2>$null
    if ($LASTEXITCODE -eq 0) { $wslOk = $true }
} catch {}

if (-not $wslOk) {
    Write-Host "`n[!] WSL installation initiated. A Windows system restart may be required to finalize virtual machine features." -ForegroundColor Yellow
    Write-Host "    After restarting Windows, simply run .\scripts\build-iso.ps1 to generate your ISO!" -ForegroundColor Cyan
    Write-Host "`nPress any key to exit..."
    [Console]::ReadKey() | Out-Null
    return
}

# 4. Execute Full ISO Build
Write-Host "`n[3/4] Launching AquaOS Immutable RootFS & ISO Builder..." -ForegroundColor Yellow
& "$ProjectRoot\scripts\build-iso.ps1"

# 5. Boot ISO in QEMU if requested and ISO exists
$targetIso = Join-Path $ProjectRoot "dist\aquaos-1.0-amd64.iso"
if (Test-Path $targetIso) {
    Write-Host "`n[4/4] AquaOS ISO Build Complete!" -ForegroundColor Green
    if (-not $SkipVmBoot) {
        Write-Host "      Starting AquaOS Virtual Machine in QEMU..." -ForegroundColor Cyan
        & "$ProjectRoot\scripts\run-vm.ps1"
    }
} else {
    Write-Host "`n[!] Build completed. Check output logs above." -ForegroundColor Yellow
}

Write-Host "`nPress any key to close this window..." -ForegroundColor DarkGray
[Console]::ReadKey() | Out-Null
