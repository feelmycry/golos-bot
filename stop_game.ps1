# Останавливает бота, API и ngrok

Get-WmiObject Win32_Process -Filter "name='python.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd -like "*bot.py*" -or $cmd -like "*api.server*") {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Остановлен: $($_.ProcessId) — $($cmd.Trim())" -ForegroundColor Yellow
    }
}

Stop-Process -Name "ngrok" -Force -ErrorAction SilentlyContinue
Write-Host "ngrok остановлен" -ForegroundColor Yellow
Write-Host "Готово." -ForegroundColor Green
