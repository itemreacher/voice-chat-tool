@echo off
setlocal enabledelayedexpansion
rem Builds a window-only (no console) %DISTDIR%\VoiceChatTool\VoiceChatTool.exe (folder build, fast start-up).
rem If the NVIDIA CUDA libraries are installed in .venv (requirements-gpu.txt),
rem they are bundled so the CPU/GPU switch works in the exe too.
cd /d "%~dp0"
if not defined DISTDIR set "DISTDIR=dist"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Create it first, see README.md.
    goto :fail
)

".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 goto :fail

set "NV_ARGS="
for /d %%D in (".venv\Lib\site-packages\nvidia\*") do (
    if exist "%%~D\bin" set NV_ARGS=!NV_ARGS! --add-binary "%%~D\bin\*;nvidia\%%~nxD\bin"
)
if defined NV_ARGS (echo Bundling NVIDIA CUDA libraries for GPU mode.) else (echo No CUDA libraries found: exe will run on CPU only.)

rem PyInstaller wipes %DISTDIR%\VoiceChatTool, so keep the user's config.toml aside.
if exist "%DISTDIR%\VoiceChatTool\config.toml" copy /y "%DISTDIR%\VoiceChatTool\config.toml" "build_config.keep" >nul

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%DISTDIR%" --onedir --windowed --name VoiceChatTool ^
    --icon assets\icon.ico --add-data "assets\logo_64.png;assets" ^
    --collect-all faster_whisper --collect-all ctranslate2 --collect-all argostranslate ^
    --collect-all sounddevice --collect-all sentencepiece --collect-all spellchecker !NV_ARGS! main.py
if errorlevel 1 goto :fail

if defined NV_ARGS ".venv\Scripts\python.exe" tools\copy_licenses.py "%DISTDIR%\VoiceChatTool"
if exist "build_config.keep" (
    copy /y "build_config.keep" "%DISTDIR%\VoiceChatTool\config.toml" >nul
    del "build_config.keep"
)
rem No config.toml is added: without one next to the exe the program uses the user data folder
rem (%APPDATA%\VoiceChatTool), exactly like the installed version.

echo.
echo Done: %DISTDIR%\VoiceChatTool\VoiceChatTool.exe
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
echo Build failed, see messages above.
if not defined NOPAUSE pause
exit /b 1
