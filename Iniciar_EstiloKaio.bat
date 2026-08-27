@echo off
setlocal
cd /d "%~dp0"
title EstiloKaio
echo ========================================
echo   Estilo Kaio
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python no esta en el PATH.
  echo Instala Python 3.11+ y volve a intentar.
  pause
  exit /b 1
)

python -m app
if errorlevel 1 (
  echo.
  echo [ERROR] Fallo el arranque.
  echo Dependencias: pip install -r scripts\requirements.txt
  pause
  exit /b 1
)

endlocal
