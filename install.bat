@echo off
title QA Proof Capture - Installer
color 0A
echo.
echo  ============================================
echo   QA Proof Capture - Installing dependencies
echo  ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version

echo.
echo Installing required packages...
pip install pillow mss opencv-python numpy --quiet --upgrade

if %errorlevel% neq 0 (
    echo [ERROR] Package installation failed.
    echo Try running this as Administrator.
    pause
    exit /b 1
)

echo.
echo [OK] All packages installed successfully!
echo.
echo Starting QA Proof Capture...
echo.
python qa_capture.py

pause
