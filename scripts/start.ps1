# Start Literature Translator (API + frontend)
# Close the browser tab to auto-stop both processes.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$Uvicorn = Join-Path $ApiDir ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path $Uvicorn)) {
  Write-Host "Creating API venv and installing deps..."
  if (-not (Test-Path $VenvPython)) {
    python3.11 -m venv (Join-Path $ApiDir ".venv")
  }
  & (Join-Path $ApiDir ".venv\Scripts\pip.exe") install -r (Join-Path $ApiDir "requirements.txt")
}

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Host "Installing frontend deps..."
  Push-Location $WebDir
  npm install
  Pop-Location
}

Write-Host "Starting API on http://127.0.0.1:8787 ..."
$api = Start-Process -FilePath $Uvicorn -ArgumentList @(
  "app.main:app",
  "--host", "127.0.0.1",
  "--port", "8787"
) -WorkingDirectory $ApiDir -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 1

Write-Host "Starting web on http://127.0.0.1:5173 ..."
$web = Start-Process -FilePath "npm" -ArgumentList @(
  "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"
) -WorkingDirectory $WebDir -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:5173/"

Write-Host ""
Write-Host "Literature Translator is running."
Write-Host "Close the browser tab to stop frontend + backend automatically."
Write-Host "Or press Ctrl+C here to exit this launcher (servers may keep running until tab close / timeout)."
Write-Host ""

try {
  Wait-Process -Id $api.Id
} catch {
  # API exited (auto-shutdown)
}

Write-Host "Services stopped."
