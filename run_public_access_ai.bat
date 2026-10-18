@echo off
title ACCESS AI - Live Server & Tunnel
echo ========================================================
echo           Starting ACCESS AI Web Navigation Server
echo ========================================================
start "ACCESS AI Flask Backend" /min cmd /c ".\venv\Scripts\python.exe app.py"
echo Waiting for Flask to initialize walking graph...
timeout /t 5 /nobreak > nul
echo Starting Public HTTPS Tunnel...
echo.
echo Live website will be accessible via: https://access-ai.loca.lt
echo ========================================================
npx --yes localtunnel --port 5000 --subdomain access-ai
pause
