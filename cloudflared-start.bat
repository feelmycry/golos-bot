@echo off
start "" "C:\Users\thisi\golos\cloudflared.exe" tunnel --url http://localhost:8000
echo Cloudflare tunnel started. Check console window for the public URL.
pause
