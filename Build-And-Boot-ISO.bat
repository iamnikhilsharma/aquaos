@echo off
title AquaOS 1.0 Beta - Automated ISO Builder and VM Launcher
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-build-environment.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Pipeline finished with code %ERRORLEVEL%.
    pause
)
