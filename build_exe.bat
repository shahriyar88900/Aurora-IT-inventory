@echo off
title Build Aurora Plant IT Inventory .exe
cd /d "%~dp0"

echo ============================================================
echo  Building Aurora Plant IT Inventory - Desktop Edition (.exe)
echo ============================================================
echo.

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

python -m pip show pywebview >nul 2>&1
if errorlevel 1 (
    echo Installing pywebview...
    python -m pip install -r requirements-desktop.txt
)

echo.
echo Building AuroraInventory.exe ...
echo.

python -m PyInstaller --noconfirm --onefile --windowed ^
    --name AuroraInventory ^
    --add-data "static;static" ^
    desktop_app.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Your app is at: dist\AuroraInventory.exe
echo.
echo  Copy AuroraInventory.exe to any folder and double-click it.
echo  A "data" folder with the database will be created next to
echo  the .exe the first time it runs.
echo ============================================================
pause
