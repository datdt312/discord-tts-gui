@echo off
setlocal
cd /d "%~dp0"
set "APPDIR=%~dp0"
set "VENV=%APPDIR%.venv-desktop"
if exist "%VENV%\Scripts\python.exe" goto dependencies
set "PYTHON_CMD=py -3.12"
%PYTHON_CMD% -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto create_venv
set "PYTHON_CMD=py -3"
%PYTHON_CMD% -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto create_venv
set "PYTHON_CMD=python"
%PYTHON_CMD% -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if errorlevel 1 goto missing_python
:create_venv
echo Preparing the desktop Python environment...
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 goto failed
:dependencies
echo Checking desktop dependencies. First launch requires an Internet connection.
"%VENV%\Scripts\python.exe" -m pip install -r "%APPDIR%requirements-desktop.txt"
if errorlevel 1 goto failed
"%VENV%\Scripts\python.exe" -c "import PyQt6.QtWidgets, edge_tts, sounddevice, imageio_ffmpeg"
if errorlevel 1 goto failed
start "Discord TTS GUI" /d "%APPDIR%" "%VENV%\Scripts\pythonw.exe" "%APPDIR%app.py"
if errorlevel 1 goto failed
exit /b 0
:missing_python
echo Install Python 3.12 from https://www.python.org/downloads/windows/ and enable its launcher.
echo Then run this file again.
pause
exit /b 1
:failed
echo.
echo Setup failed. Read the error above, check your connection and Python installation, then retry.
pause
exit /b 1
