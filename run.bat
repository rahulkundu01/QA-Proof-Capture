@echo off
title QA Proof Capture
cd /d "%~dp0"
python qa_capture.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start. Run install.bat first.
    pause
)
