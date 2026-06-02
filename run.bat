@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ===================================================
    echo [ERROR] Python not found!
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check "Add python.exe to PATH"
    echo ===================================================
    pause
    exit /b
)

:: Setup venv if not exists
if not exist "env\Scripts\python.exe" (
    echo ===================================================
    echo [INFO] First run - setting up virtual environment...
    echo ===================================================
    python -m venv env
    echo.
    echo [INFO] Installing dependencies...
    env\Scripts\pip.exe install selenium webdriver-manager requests Pillow ddddocr PySide6 mss opencv-python onnxruntime -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    echo ===================================================
    echo [OK] Environment ready!
    echo ===================================================
    timeout /t 2 >nul
)

echo.
echo ===================================================
echo   LibSeat Allocator Starting...
echo ===================================================
start "LibSeat Allocator" env\Scripts\pythonw.exe app.py

echo.
echo App launched! You can close this window.
timeout /t 3 >nul
