@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist "env\Scripts\python.exe" (
    set "PY=env\Scripts\python.exe"
) else (
    set "PY=python"
)

echo ==================================================
echo   Building LNU-LibSeat exe package
echo ==================================================
"%PY%" build.py --index-url https://pypi.tuna.tsinghua.edu.cn/simple %*

echo.
if %errorlevel% neq 0 (
    echo [FAIL] Build failed.
) else (
    echo [OK] Build finished. See dist folder.
)
pause
