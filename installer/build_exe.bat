@echo off
REM Builds VirtualXboxMapper.exe with PyInstaller, then (if Inno Setup is
REM installed) the VirtualXboxMapper-Setup-<version>.exe installer.
REM Run from anywhere; it switches to the repository root itself.

setlocal
cd /d "%~dp0\.."

echo [1/4] Installing dependencies...
python -m pip install --upgrade -r requirements.txt -r requirements-build.txt || goto :fail

echo [2/4] Running tests...
python -m pytest -q tests || goto :fail

echo [3/4] Building executable...
if exist "build\work" rmdir /s /q "build\work"
if exist "build\dist\VirtualXboxMapper" rmdir /s /q "build\dist\VirtualXboxMapper"
python -m PyInstaller --noconfirm --clean installer\VirtualXboxMapper.spec --distpath build\dist --workpath build\work || goto :fail
if not exist "build\dist\VirtualXboxMapper\VirtualXboxMapper.exe" goto :fail

for /f "delims=" %%V in ('python tools\app_version.py') do set "APPVER=%%V"
echo Version: %APPVER%

echo [4/4] Building installer...
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
)
if "%ISCC%"=="" (
    echo Inno Setup 6 not found - skipping the installer. Get it from https://jrsoftware.org/isinfo.php
    echo Executable: build\dist\VirtualXboxMapper\VirtualXboxMapper.exe
    goto :done
)
if exist "build\installer_output" rmdir /s /q "build\installer_output"
"%ISCC%" /DMyAppVersion=%APPVER% installer\setup.iss || goto :fail
echo Installer written to build\installer_output\

:done
echo.
echo Build complete.
endlocal
exit /b 0

:fail
echo.
echo BUILD FAILED - scroll up for the error.
endlocal
exit /b 1
