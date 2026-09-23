@echo off
setlocal
title Aurora Plant IT Inventory - Database Backup
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python 3 was not found.
    pause
    exit /b 1
)

%PYTHON_CMD% backup_database.py
if errorlevel 1 (
    echo Backup failed.
    pause
    exit /b 1
)

echo.
echo Backup completed successfully.
echo See the backups folder.
echo.
pause

