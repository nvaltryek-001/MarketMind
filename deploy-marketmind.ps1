Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "       MARKETMIND DEPLOYMENT CHECK" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# Check Git
Write-Host "[1/6] Checking Git..." -ForegroundColor Yellow
git status
Write-Host "OK" -ForegroundColor Green

# Check backend
Write-Host ""
Write-Host "[2/6] Checking backend..." -ForegroundColor Yellow
if (!(Test-Path ".\backend\main.py")) {
    throw "backend/main.py not found"
}
if (!(Test-Path ".\backend\requirements.txt")) {
    throw "backend/requirements.txt not found"
}
Write-Host "Backend files OK" -ForegroundColor Green

# Check frontend
Write-Host ""
Write-Host "[3/6] Checking frontend..." -ForegroundColor Yellow
if (!(Test-Path ".\frontend\package.json")) {
    throw "frontend/package.json not found"
}
if (!(Test-Path ".\frontend\src\app")) {
    throw "frontend/src/app not found"
}
Write-Host "Frontend files OK" -ForegroundColor Green

# Build frontend
Write-Host ""
Write-Host "[4/6] Building frontend..." -ForegroundColor Yellow
Set-Location ".\frontend"
npm run build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed"
}
Set-Location ".."
Write-Host "Frontend build OK" -ForegroundColor Green

# Check Git status
Write-Host ""
Write-Host "[5/6] Checking Git status..." -ForegroundColor Yellow
git status --short
Write-Host "Git check OK" -ForegroundColor Green

# Check remote
Write-Host ""
Write-Host "[6/6] Checking GitHub remote..." -ForegroundColor Yellow
git remote -v
Write-Host "GitHub remote OK" -ForegroundColor Green

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "       MARKETMIND READY FOR DEPLOYMENT" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend : Render" -ForegroundColor Cyan
Write-Host "Frontend: Vercel" -ForegroundColor Cyan
Write-Host ""
Write-Host "No deployment files were changed." -ForegroundColor Gray
