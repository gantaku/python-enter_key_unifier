@echo off
echo ========================================
echo Enter Key Unifier - Build Script
echo ========================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo [2/3] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

echo [3/3] Building exe file...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name enter_key_unifier ^
    --distpath build ^
    --hidden-import pystray._win32 ^
    --noconfirm ^
    run.py
if %errorlevel% neq 0 (
    echo ERROR: Build failed
    pause
    exit /b 1
)
echo.

if exist build\enter_key_unifier.exe (
    echo SUCCESS: build\enter_key_unifier.exe
) else (
    echo ERROR: exe file was not generated
    pause
    exit /b 1
)

if exist enter_key_unifier.spec del /q enter_key_unifier.spec
