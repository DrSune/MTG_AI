# MTG AI Training Runner
# This script finds the best Python executable and starts the Pro-Scale training.

$workingPython = "C:\Program Files\Python312\python.exe"

if (-not (Test-Path $workingPython)) {
    Write-Host "Error: C:\Program Files\Python312\python.exe not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Using Python: $workingPython" -ForegroundColor Cyan
Write-Host "Starting MTG AI Pro-Scale Foundation Training..." -ForegroundColor Green
Write-Host "Mode: 1024-dim, 16-layers, 50k-vocab, Foundation Phase (1000 games)" -ForegroundColor Yellow

# Execute the training module
& $workingPython -m MTG_bot.main_train
