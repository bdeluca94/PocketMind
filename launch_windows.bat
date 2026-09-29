@echo off
title PocketMind
cd /d "%~dp0"

set VENV_DIR=%~dp0.venv-win

if exist "%VENV_DIR%\Scripts\python.exe" goto :run

if exist "%~dp0PocketMind.exe" (
    echo.
    echo  PocketMind.exe is already in this folder - double-click that
    echo  instead if you don't have an internet connection right now.
    echo  It needs no setup and no internet at all.
    echo.
    echo  This launcher ^(launch_windows.bat^) is a separate option for
    echo  running from the Python source directly, and it does still need
    echo  an internet connection for its one-time setup below.
    echo.
)

echo.
echo  ============================================
echo   PocketMind - first time setup
echo  ============================================
echo.
echo  This will take a few minutes and needs an
echo  internet connection. It only happens once.
echo.

REM `where python` isn't reliable here: Windows ships built-in stub
REM python.exe/python3.exe files (the "App execution aliases") that exist
REM on disk and satisfy `where`, but do nothing except redirect to the
REM Microsoft Store when run. Actually invoking python and checking its
REM exit code catches that case; `where` alone does not.
python --version >nul 2>nul
if errorlevel 1 goto :nopython
goto :havepython

:nopython
echo  Python was not found on this PC.
echo.
echo  If a Microsoft Store prompt just opened ^(or offered to^), that's a
echo  built-in Windows shortcut, not a real Python install - close it.
echo.
if exist "%~dp0prerequisites\python-3.12.10-amd64.exe" (
    echo  A Python installer is included on this drive, so you don't need
    echo  internet for this step: double-click
    echo    prerequisites\python-3.12.10-amd64.exe
    echo  and check "Add python.exe to PATH" during install, then run this
    echo  file again.
) else (
    echo  Install Python from https://python.org instead ^(check "Add
    echo  python.exe to PATH" during install^), then run this file again.
)
echo.
echo  If Python IS already installed and you still see this message,
echo  turn off the conflicting shortcut at: Settings ^> Apps ^> Advanced
echo  app settings ^> App execution aliases ^> turn OFF "python.exe" and
echo  "python3.exe", then run this file again.
echo.
pause
exit /b 1

:havepython
python -m venv "%VENV_DIR%"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo  Couldn't create the app's Python environment. Make sure you
    echo  have a working internet connection and enough free disk space,
    echo  then run this file again. If it keeps happening, try
    echo  reinstalling Python from https://python.org.
    echo.
    pause
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet

echo  Setting up the AI engine...

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    echo  NVIDIA graphics card detected - installing the
    echo  GPU-accelerated version for faster responses.
    REM --only-binary=:all: and a specific pinned version both matter here:
    REM this index doesn't always have a prebuilt wheel for whatever the
    REM newest llama-cpp-python release is, and without --only-binary pip's
    REM default fallback is to try building that unavailable version from
    REM source instead - which fails outright on a PC with no C++ compiler
    REM installed, the common case. Pinning to a version confirmed to have
    REM a prebuilt wheel on this index sidesteps that entirely.
    pip install --only-binary=:all: llama-cpp-python==0.3.4 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --quiet
    REM The GPU wheel installs fine on its own even without a full CUDA
    REM Toolkit on this PC - but it still needs these two small runtime
    REM packages (not the ~3GB Toolkit; just the couple of DLLs llama.cpp's
    REM CUDA backend actually calls) to find its CUDA libraries at import
    REM time. Always attempted regardless of whether the line above
    REM succeeded. so the check below sees a consistent, complete picture
    REM either way rather than depending on this one too.
    pip install "nvidia-cublas-cu12==12.1.3.1" "nvidia-cuda-runtime-cu12==12.1.105" --quiet
) else (
    echo  No NVIDIA graphics card detected - installing the
    echo  standard version ^(runs on your PC's processor^).
    pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --quiet
)

REM Confirmed working here, not just "pip said yes": a wheel can install
REM cleanly and still fail to actually load (a GPU PC missing the two
REM packages above used to fail here with a missing-DLL error that had
REM nothing to do with any of the causes listed further down). A bare
REM `import llama_cpp` isn't a valid way to check that, though - it would
REM fail even when the GPU build is genuinely fine, since only server.py's
REM own startup (_add_cuda_dll_directories) points Windows at the CUDA
REM DLLs above before importing; this inline equivalent is what makes the
REM check reflect how the app actually loads it. On a CPU-only install
REM (or no GPU detected above), the directories below simply don't exist
REM and this behaves exactly like a bare import.
python -c "import os,sys; from pathlib import Path; b=Path(sys.prefix)/'Lib'/'site-packages'; d=[b/'nvidia'/'cublas'/'bin', b/'nvidia'/'cuda_runtime'/'bin', b/'llama_cpp'/'lib']; [os.add_dll_directory(str(p)) for p in d if p.is_dir()]; os.environ['PATH']=os.pathsep.join(str(p) for p in d if p.is_dir())+os.pathsep+os.environ.get('PATH',''); import llama_cpp" >nul 2>nul
if errorlevel 1 (
    echo  GPU version didn't work on this PC - using the
    echo  standard version instead. The app will still work.
    pip uninstall llama-cpp-python nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 -y --quiet >nul 2>nul
    pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --quiet
)

REM Check the actual outcome rather than trying to track errorlevel through
REM everything above - either path can still fail for reasons unrelated to
REM GPU vs CPU at all (disk space, a dropped connection, Windows long-path
REM limits), and this is the one place that catches all of them before the
REM script declares success. Same DLL-aware check as above, re-run fresh
REM rather than trusting the errorlevel from before the fallback block -
REM it needs to reflect the CPU reinstall too if that just happened.
python -c "import os,sys; from pathlib import Path; b=Path(sys.prefix)/'Lib'/'site-packages'; d=[b/'nvidia'/'cublas'/'bin', b/'nvidia'/'cuda_runtime'/'bin', b/'llama_cpp'/'lib']; [os.add_dll_directory(str(p)) for p in d if p.is_dir()]; os.environ['PATH']=os.pathsep.join(str(p) for p in d if p.is_dir())+os.pathsep+os.environ.get('PATH',''); import llama_cpp" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Couldn't install the AI engine ^(llama-cpp-python^). Common
    echo  causes, most likely first:
    echo.
    echo   - The Microsoft Visual C++ Runtime isn't installed - a lot of
    echo     bare/fresh Windows PCs are missing it. An installer is
    echo     included on this drive: double-click
    echo     prerequisites\vc_redist.x64.exe, then run this file again.
    echo   - Windows Long Path support is off. As Administrator, open
    echo     PowerShell and run:
    echo       New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
    echo     then restart your PC and try again.
    echo   - Running out of disk space ^(if you're running this from a
    echo     USB drive, copy the app to your PC's hard drive first^).
    echo   - An interrupted download.
    echo   - No ready-made version was available to download for this
    echo     PC's exact setup, so it tried to build one here instead,
    echo     which needs Microsoft's C++ Build Tools ^(a separate,
    echo     large download from
    echo     https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo     - choose the "Desktop development with C++" workload^).
    echo.
    echo  Scroll up for the actual error, then run this file again.
    echo.
    pause
    exit /b 1
)

pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  Setup hit a problem installing the app's dependencies. Check
    echo  your internet connection and try running this file again.
    echo.
    pause
    exit /b 1
)

echo.
echo  Setup complete!
echo.

:run
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo  Couldn't activate the app's Python environment - it may be
    echo  damaged. Delete the ".venv-win" folder next to this file and
    echo  run it again to redo first-time setup.
    echo.
    pause
    exit /b 1
)
echo  Starting PocketMind...
echo  A browser window will open shortly.
echo  ^(Keep this window open while you use the app.^)
echo.
python backend\server.py
pause
