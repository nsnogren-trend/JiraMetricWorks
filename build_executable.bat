@echo off
echo Building JiraMetricWorks executable...
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Clean previous build
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM Build the executable
echo Running PyInstaller...
pyinstaller JiraMetricWorks.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===================================
    echo Build completed successfully!
    echo.
    echo Your executable is located at:
    echo %CD%\dist\JiraMetricWorks.exe
    echo.
    echo You can now run this executable directly on any Windows machine
    echo without needing Python installed.
    echo ===================================
) else (
    echo.
    echo ===================================
    echo Build failed! Check the error messages above.
    echo ===================================
)

pause
