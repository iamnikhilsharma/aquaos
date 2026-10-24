@echo off
title AquaOS 1.0 Beta Virtual Machine Launcher
cls
echo ==================================================================
echo   AquaOS 1.0 Beta - Virtual Machine Launcher
echo ==================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-vm.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo VM exited with code %ERRORLEVEL%.
    pause
)
