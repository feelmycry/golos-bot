# Автозапуск: ngrok + API сервер + бот (все в фоне, логи в файлы)

$ProjectDir = "C:\Users\thisi\golos"
$MiniAppDir = "$ProjectDir\miniapp"
$LogDir     = "$ProjectDir\logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Set-Location $ProjectDir

# --- 1. Убиваем старые процессы бота и API (не ngrok) ---
Get-WmiObject Win32_Process -Filter "name='python.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd -like "*bot.py*" -or $cmd -like "*api.server*") {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2

# --- 2. Запускаем ngrok (если не запущен) ---
$ngrokUrl = $null
try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
    $ngrokUrl = $tunnels.tunnels[0].public_url
    Write-Host "[ngrok] уже запущен: $ngrokUrl" -ForegroundColor Green
} catch {
    Write-Host "[ngrok] запускаем..." -ForegroundColor Yellow
    Start-Process -FilePath "ngrok" -ArgumentList "http 8000" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    try {
        $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 5
        $ngrokUrl = $tunnels.tunnels[0].public_url
        Write-Host "[ngrok] готов: $ngrokUrl" -ForegroundColor Green
    } catch {
        Write-Host "[ОШИБКА] ngrok не запустился. Запустите ngrok вручную: ngrok http 8000" -ForegroundColor Red
        exit 1
    }
}

# --- 3. Обновляем .env.production если URL изменился ---
$envProdFile = "$MiniAppDir\.env.production"
$currentEnvUrl = (Get-Content $envProdFile | Where-Object { $_ -match "VITE_API_URL" }) -replace "VITE_API_URL=", ""

if ($currentEnvUrl -ne $ngrokUrl) {
    Write-Host "[frontend] ngrok URL изменился ($currentEnvUrl → $ngrokUrl). Пересобираем..." -ForegroundColor Yellow
    "VITE_API_URL=$ngrokUrl" | Set-Content -Path $envProdFile -Encoding utf8
    Set-Location $MiniAppDir
    npm run build 2>&1 | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
    Write-Host "[frontend] деплой на Vercel..." -ForegroundColor Yellow
    npx vercel deploy dist --prod --yes 2>&1 | Select-String -Pattern "(Aliased|Error)" | ForEach-Object { Write-Host "  $_" }
    Set-Location $ProjectDir
    Write-Host "[frontend] обновлён" -ForegroundColor Green
} else {
    Write-Host "[frontend] URL не изменился, пересборка не нужна" -ForegroundColor Green
}

# --- 4. Запускаем FastAPI в фоне (лог в файл) ---
Write-Host "[API] запускаем сервер на порту 8000..." -ForegroundColor Yellow
$apiLog = "$LogDir\api.log"
Start-Process -FilePath "python" -ArgumentList "-m api.server" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError "$LogDir\api_err.log"

Start-Sleep -Seconds 2

# --- 5. Запускаем бота в фоне (лог в файл) ---
Write-Host "[бот] запускаем..." -ForegroundColor Yellow
$botLog = "$LogDir\bot.log"
Start-Process -FilePath "python" -ArgumentList "bot.py" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $botLog `
    -RedirectStandardError "$LogDir\bot_err.log"

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " Всё запущено в фоне!" -ForegroundColor Cyan
Write-Host " Mini App: https://dist-roan-gamma-70.vercel.app" -ForegroundColor Cyan
Write-Host " API:      $ngrokUrl" -ForegroundColor Cyan
Write-Host " Логи:     $LogDir\" -ForegroundColor Cyan
Write-Host "  - bot.log / bot_err.log" -ForegroundColor Cyan
Write-Host "  - api.log / api_err.log" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Чтобы остановить всё: запустите stop_game.ps1" -ForegroundColor Yellow
