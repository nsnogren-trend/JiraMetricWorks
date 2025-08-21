# PowerShell script to build JiraMetricWorks executable
Write-Host "Building JiraMetricWorks executable..." -ForegroundColor Green
Write-Host ""

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# Clean previous build
Write-Host "Cleaning previous build files..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Build the executable
Write-Host "Running PyInstaller..." -ForegroundColor Yellow
& pyinstaller JiraMetricWorks.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "===================================" -ForegroundColor Green
    Write-Host "Build completed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your executable is located at:" -ForegroundColor Cyan
    Write-Host "$PWD\dist\JiraMetricWorks.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "You can now run this executable directly on any Windows machine" -ForegroundColor Green
    Write-Host "without needing Python installed." -ForegroundColor Green
    Write-Host "===================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "===================================" -ForegroundColor Red
    Write-Host "Build failed! Check the error messages above." -ForegroundColor Red
    Write-Host "===================================" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
