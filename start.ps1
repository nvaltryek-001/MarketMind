# FinSight Startup Script
# Starts both backend (FastAPI) and frontend (Next.js) simultaneously

$projectRoot = $PSScriptRoot

# Kill any existing processes on ports 8001 and 3000
$ports = @(8001, 3000)
foreach ($port in $ports) {
    $process = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if ($process) {
        Stop-Process -Id $process -Force -ErrorAction SilentlyContinue
        Write-Host "Killed process on port $port" -ForegroundColor Yellow
    }
}

# Start Backend
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Starting FinSight Backend (FastAPI)  " -ForegroundColor Cyan
Write-Host "  URL: http://localhost:8001            " -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:8001/docs    " -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$backendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
} -ArgumentList $projectRoot

# Wait for backend to be ready
Write-Host "Waiting for backend to start..." -ForegroundColor Gray
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "Backend is ready!`n" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
}

# Start Frontend
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting FinSight Frontend (Next.js)   " -ForegroundColor Cyan
Write-Host "  URL: http://localhost:3000            " -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$frontendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location "$root\frontend"
    $env:NEXT_PUBLIC_API_URL = "http://localhost:8001"
    npm run dev
} -ArgumentList $projectRoot

# Wait for frontend to be ready
Write-Host "Waiting for frontend to start..." -ForegroundColor Gray
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "Frontend is ready!`n" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  FinSight is now running!              " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Dashboard: http://localhost:3000      " -ForegroundColor White
Write-Host "  API:       http://localhost:8001      " -ForegroundColor White
Write-Host "  API Docs:  http://localhost:8001/docs " -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop both services`n" -ForegroundColor Yellow

# Keep script running and show output
while ($true) {
    $backendOutput = Receive-Job -Job $backendJob
    $frontendOutput = Receive-Job -Job $frontendJob
    
    if ($backendOutput) {
        Write-Host "[BACKEND] $backendOutput" -ForegroundColor Blue
    }
    if ($frontendOutput) {
        Write-Host "[FRONTEND] $frontendOutput" -ForegroundColor Magenta
    }
    
    if ($backendJob.State -eq "Failed" -or $frontendJob.State -eq "Failed") {
        Write-Host "`nOne of the services failed!" -ForegroundColor Red
        break
    }
    
    Start-Sleep -Milliseconds 100
}

# Cleanup
Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
Remove-Job -Job $backendJob -ErrorAction SilentlyContinue
Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
Remove-Job -Job $frontendJob -ErrorAction SilentlyContinue

Write-Host "`nFinSight stopped." -ForegroundColor Yellow
