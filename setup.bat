@echo off
echo 🚶‍♂️ Privilege Walk Application Setup
echo ======================================
echo.

REM Check if UV is installed
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ UV is not installed. Please install UV first:
    echo    Visit: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

echo ✅ UV is installed

REM Check if we're in the right directory
if not exist "pyproject.toml" (
    echo ❌ Please run this script from the project directory
    pause
    exit /b 1
)

echo ✅ Project directory found

REM Sync the UV environment
echo 📦 Syncing UV environment...
uv sync

if %errorlevel% equ 0 (
    echo ✅ UV environment is ready!
    echo.
    echo 🚀 You can now run the application with:
    echo    run.bat
    echo    or
    echo    uv run python run.py
    echo.
    echo 📱 The application will be available at: http://localhost:5001
) else (
    echo ❌ Failed to sync UV environment
)

pause 