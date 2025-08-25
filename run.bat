@echo off
echo 🚶‍♂️ Privilege Walk Application
echo ========================================
echo.
echo Starting the application using UV environment...
echo.
echo 📱 Open your browser to: http://localhost:5001
echo 🔗 Students will connect via your computer's IP address
echo.
echo 💡 Tips:
echo    - Make sure all devices are on the same network
echo    - Test the QR code with one student first
echo    - Press Ctrl+C to stop the server
echo.
echo ========================================
echo.

REM Use UV to run the application
uv run python run.py

pause 