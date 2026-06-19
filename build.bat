@echo off
echo Checking and installing PyInstaller...
py -m pip install pyinstaller
echo.
echo Building standalone executable using PyInstaller spec...
py -m PyInstaller TimeTracker.spec
echo.
echo Build process complete. Check the 'dist' folder for TimeTracker.exe.
pause
