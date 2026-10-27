@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo No se encontro Python. Instala Python 3 y activa la opcion de agregarlo al PATH.
  pause
  exit /b 1
)
python actualizar.py
powershell.exe -NoProfile -Command "$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if (-not $listener) { $pythonPath = (Get-Command python).Source; $process = Start-Process -FilePath $pythonPath -ArgumentList '-I servidor_local.py' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -RedirectStandardOutput 'trabajo/servidor-local.log' -RedirectStandardError 'trabajo/servidor-local-error.log' -PassThru; $process.Id | Set-Content 'trabajo/servidor-local.pid' }; $ready = $false; for ($i = 0; $i -lt 30; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8765/api/fuentes' -TimeoutSec 1; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}; Start-Sleep -Milliseconds 200 }; if (-not $ready) { Write-Host 'No se pudo iniciar el tablero. Revisa si el puerto 8765 esta ocupado y trabajo/servidor-local-error.log.'; exit 1 }"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" http://127.0.0.1:8765/index.html
