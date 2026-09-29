@echo off
setlocal
cd /d "%~dp0\.."

echo Building the standalone Windows app (PocketMind.exe)...
echo This runs once, on a Windows PC, to produce the .exe.
echo.

REM `where python` isn't reliable here: Windows ships built-in stub
REM python.exe/python3.exe files (the "App execution aliases") that can
REM exist on PATH even with no real Python installed. Actually invoking
REM python and checking its exit code catches that; `where` alone does not.
python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this PC ^(or only the Windows Store's
    echo placeholder python.exe is on PATH^).
    echo.
    echo Install Python from https://python.org ^(check "Add python.exe
    echo to PATH" during install^), then run this file again.
    echo.
    echo If Python IS already installed and you still see this message,
    echo turn off the conflicting shortcut at: Settings ^> Apps ^>
    echo Advanced app settings ^> App execution aliases ^> turn OFF
    echo "python.exe" and "python3.exe".
    echo.
    pause
    exit /b 1
)

python -m venv .venv-build-win
if not exist ".venv-build-win\Scripts\python.exe" (
    echo.
    echo Couldn't create the build's Python environment. Check your
    echo internet connection and free disk space, then try again.
    echo.
    pause
    exit /b 1
)

call .venv-build-win\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

echo Installing dependencies (GPU-accelerated build - still runs fine on a
echo PC with no NVIDIA GPU, just without the speedup)...
REM --only-binary=:all: and a specific pinned version both matter here:
REM this index doesn't always have a prebuilt wheel for whatever the
REM newest llama-cpp-python release is, and without --only-binary pip's
REM default fallback is to try building that unavailable version from
REM source instead - which fails outright without a C++ compiler. Pinning
REM to a version confirmed to have a prebuilt wheel on this index sidesteps
REM that entirely.
pip install --only-binary=:all: llama-cpp-python==0.3.4 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --quiet
if errorlevel 1 goto :installfail
REM The GPU wheel above installs and runs fine without a full CUDA Toolkit
REM on the end user's PC - but it still needs these two small runtime
REM packages (not the ~3GB Toolkit; just the couple of DLLs llama.cpp's
REM CUDA backend actually calls) bundled into the .exe alongside it, or a
REM GPU PC would fail to load the model at all with a missing-DLL error
REM instead of falling back to CPU. server.py's own startup
REM (_add_cuda_dll_directories) is what points Windows at these once
REM they're bundled in; see the --collect-all lines below for the bundling
REM itself.
pip install "nvidia-cublas-cu12==12.1.3.1" "nvidia-cuda-runtime-cu12==12.1.105" --quiet
if errorlevel 1 goto :installfail
pip install -r backend\requirements.txt --quiet
if errorlevel 1 goto :installfail
pip install pyinstaller --quiet
if errorlevel 1 goto :installfail

REM stable-diffusion-cpp-python (image generation) has no prebuilt wheel for
REM this platform anywhere - unlike llama-cpp-python above, pip always
REM builds it from source here, which needs an actual C++ compiler on PATH.
REM A plain double-click of this .bat doesn't have one there by default even
REM once Visual Studio Build Tools is installed - only a Developer Command
REM Prompt does - so this locates and runs that environment's own setup
REM script first, in this same process, rather than assuming the user
REM launched one themselves.
set VCVARS=
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if exist "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set VCVARS=C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" set VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat
if "%VCVARS%"=="" (
    echo.
    echo Image generation needs a C++ compiler to build one dependency
    echo ^(stable-diffusion-cpp-python^) from source, and none was found on
    echo this PC. Install Visual Studio Build Tools with the "Desktop
    echo development with C++" workload from
    echo https://visualstudio.microsoft.com/visual-cpp-build-tools/, then
    echo run this file again.
    echo.
    pause
    exit /b 1
)
call "%VCVARS%"
pip install stable-diffusion-cpp-python --quiet
if errorlevel 1 goto :installfail
goto :dependencies_ok

:installfail
echo.
echo Setup hit a problem installing dependencies. Common causes, most
echo likely first:
echo.
echo  - Windows Long Path support is off. As Administrator, open
echo    PowerShell and run:
echo      New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
echo    then restart your PC and try again.
echo  - Running out of disk space. Building needs a few GB free. If
echo    you're building directly on a USB drive, copy this whole folder
echo    to your PC's hard drive first, build there, then copy just the
echo    finished PocketMind.exe onto the USB drive afterward.
echo  - An internet connection that dropped mid-download.
echo  - No ready-made version was available to download for this PC's
echo    exact setup, so it tried to build one here instead, which needs
echo    Microsoft's C++ Build Tools ^(a separate, large download from
echo    https://visualstudio.microsoft.com/visual-cpp-build-tools/ -
echo    choose the "Desktop development with C++" workload^).
echo.
echo Scroll up for the actual error, then try again.
echo.
pause
exit /b 1

:dependencies_ok

echo Building executable...
pyinstaller --onefile --name PocketMind ^
  --icon assets\icon.ico ^
  --add-data "frontend;frontend" ^
  --collect-all llama_cpp ^
  --collect-all nvidia.cublas ^
  --collect-all nvidia.cuda_runtime ^
  --collect-all stable_diffusion_cpp ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --collect-all pypdfium2 ^
  --collect-all pypdfium2_raw ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --paths backend ^
  backend\server.py

if not exist "dist\PocketMind.exe" (
    echo.
    echo Build did not produce dist\PocketMind.exe - something went
    echo wrong above. Scroll up for the actual error from pyinstaller.
    echo.
    pause
    exit /b 1
)

echo.
echo Done. Find PocketMind.exe in the "dist" folder.
echo Copy it to the root of the USB drive (next to the "frontend" folder
echo is NOT needed anymore - the .exe has it built in).
pause
