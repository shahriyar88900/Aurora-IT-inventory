@echo off
title Aurora Plant IT Inventory - Desktop
cd /d "%~dp0"

python -c "import webview" 2>nul
if errorlevel 1 (
    echo First-time setup: installing the desktop window component...
    echo ^(pywebview - only needed once^)
    python -m pip install -r requirements-desktop.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install pywebview. Check your internet connection
        echo and that Python/pip are installed and on PATH, then try again.
        pause
        exit /b 1
    )
)

python desktop_app.py
if errorlevel 1 (
    echo.
    echo The app closed with an error. See the message above.
    pause
)
