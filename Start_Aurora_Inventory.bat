@echo off
setlocal
title Aurora Plant IT Inventory Server
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo.
    echo Python 3 is not installed or is not available in PATH.
    echo Install Python 3.11 or newer and select "Add Python to PATH".
    echo https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo             Aurora IT INVENTORY - VERSION 4.0
echo ============================================================
echo.
echo LOGIN-FIRST RELEASE - OLD PORT 8080 IS NOT USED
echo Server PC:   http://localhost:8090/login
echo Office LAN:  http://THIS-PC-IP:8090/login
echo Run time:    8 hours, then automatic shutdown
echo.
echo To find this PC's IP, run Show_Server_IP.bat.
echo Keep this window open. Press Ctrl+C to stop the server.
echo.

set "APS_RUN_HOURS=8"
set "APS_OPEN_BROWSER=1"
set "APS_PORT=8090"
%PYTHON_CMD% server.py

echo.
echo The Aurora Plant IT Inventory server has stopped.
pause
