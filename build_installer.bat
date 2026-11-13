@echo off
setlocal
rem Builds the Windows installers: installer\Output\VoiceChatTool-Setup-<version>-CPU.exe and -GPU.exe
rem Needs Inno Setup 6 (winget install JRSoftware.InnoSetup). Set SKIPBUILD=1 to reuse dist\.
cd /d "%~dp0"
if not defined DISTDIR set "DISTDIR=dist"

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup
    goto :fail
)

for /f %%V in ('.venv\Scripts\python.exe tools\version.py') do set "VER=%%V"
echo Version %VER%

if not defined SKIPBUILD (
    set NOPAUSE=1
    call "%~dp0build.bat"
    if errorlevel 1 goto :fail
)
if not exist "%DISTDIR%\VoiceChatTool\VoiceChatTool.exe" goto :fail

"%ISCC%" /Qp /DAppVersion=%VER% "/DDistDir=%CD%\%DISTDIR%" installer\VoiceChatTool.iss
if errorlevel 1 goto :fail
if exist "%DISTDIR%\VoiceChatTool\_internal\nvidia" (
    "%ISCC%" /Qp /DAppVersion=%VER% "/DDistDir=%CD%\%DISTDIR%" /DGPU=1 installer\VoiceChatTool.iss
    if errorlevel 1 goto :fail
) else (
    echo No CUDA libraries in the build: only the CPU installer was created.
)

echo.
echo Done. Installers are in installer\Output
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
echo Installer build failed, see messages above.
if not defined NOPAUSE pause
exit /b 1
