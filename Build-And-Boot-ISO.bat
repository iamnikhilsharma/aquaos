@echo off
title AquaOS 1.0 Beta - ISO Builder and QEMU Launcher
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File scripts\build-iso.ps1
if exist "dist\aquaos-1.0-amd64.iso" (
    powershell -ExecutionPolicy Bypass -File scripts\run-qemu.ps1
)
pause
