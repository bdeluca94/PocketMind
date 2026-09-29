@echo off
title PocketMind - Desktop Shortcut
cd /d "%~dp0"

set DESKTOP=%USERPROFILE%\Desktop
if not exist "%DESKTOP%" (
    echo.
    echo  Couldn't find a Desktop folder on this computer ^(%DESKTOP%^).
    echo.
    pause
    exit /b 1
)

if exist "%~dp0PocketMind.exe" (
    set TARGET=%~dp0PocketMind.exe
) else (
    set TARGET=%~dp0launch_windows.bat
)

REM A single inline PowerShell command, not a script file written to disk
REM and then executed. That's deliberate: the "batch generates a script and
REM runs it" pattern (the previous version of this file used cscript + a
REM temp .vbs) is a well-known signature antivirus heuristics watch for,
REM regardless of what the generated script actually does. Nothing is
REM written to disk here at all, so that specific trigger doesn't apply.
REM This does NOT address the separate, more likely cause of a Windows
REM SmartScreen warning on this file itself (see README.md) - that's about
REM this .bat file's own origin (Mark of the Web from the downloaded zip)
REM and has the same fix regardless of what the file does internally.
REM IconLocation is set explicitly rather than left to inherit from the
REM target - the fallback target (launch_windows.bat) would otherwise show
REM a generic batch-file icon instead of PocketMind's own.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut('%DESKTOP%\PocketMind.lnk'); $l.TargetPath = '%TARGET%'; $l.WorkingDirectory = '%~dp0'; $l.Description = 'PocketMind'; $l.IconLocation = '%~dp0assets\icon.ico'; $l.Save()" >nul 2>nul

if exist "%DESKTOP%\PocketMind.lnk" (
    echo.
    echo  Done! A PocketMind shortcut is now on your Desktop.
    echo.
    echo  It points at this drive, so it only works while the drive is
    echo  plugged in, and it can break if the drive is later assigned a
    echo  different letter ^(e.g. E: becomes F: on a different USB port^).
    echo  If that happens, just run this file again to fix it.
    echo.
) else (
    echo.
    echo  Couldn't create the shortcut - this computer may block PowerShell
    echo  via Group Policy or antivirus software. You can also right-click
    echo  launch_windows.bat and choose "Send to ^> Desktop ^(create
    echo  shortcut^)" to do it yourself instead.
    echo.
)

pause
