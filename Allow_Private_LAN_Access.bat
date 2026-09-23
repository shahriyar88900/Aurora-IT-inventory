@echo off
setlocal
title Aurora Plant IT Inventory - Windows Firewall Setup

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo Administrator permission is required.
    echo Right-click this file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="Aurora Plant IT Inventory - Private LAN" >nul 2>&1
netsh advfirewall firewall add rule name="Aurora Plant IT Inventory - Private LAN" dir=in action=allow protocol=TCP localport=8090 profile=private,public >nul

if errorlevel 1 (
    echo Firewall rule could not be created.
    pause
    exit /b 1
)

echo.
echo Windows Firewall is ready.
echo TCP port 8090 is allowed from any device on the same network the
echo server PC is connected to (wired LAN or WiFi), regardless of subnet.
echo.
pause
