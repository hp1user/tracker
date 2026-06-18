@echo off
echo Checking and installing PyInstaller...
python -m pip install pyinstaller
echo.
echo Building standalone executable using PyInstaller spec...
python -m PyInstaller TimeTracker.spec
echo.
echo Build process complete. Check the 'dist' folder for TimeTracker.exe.
pause
