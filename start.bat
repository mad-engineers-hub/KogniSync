@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo              KOGNISYNC LAUNCHER
echo =====================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_kognisync.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% NEQ 0 (
    echo.
    echo [!] KogniSync startup stopped with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
