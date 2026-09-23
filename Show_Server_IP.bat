@echo off
setlocal
title Aurora Plant IT Inventory - Server IP
echo.
echo Open this address from another office PC:
echo.
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -ne '127.0.0.1' } | ForEach-Object { 'http://' + $_.IPAddress + ':8090/login' }"
echo.
echo If no address is shown, confirm this PC is connected to a network
echo (wired LAN or WiFi).
echo.
pause
