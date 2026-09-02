@echo off
chcp 65001 >nul
cd /d "%~dp0.."
color 0A
title Estilo Kaio - Verificador

echo ==========================================
echo    VERIFICADOR - Estilo Kaio
echo ==========================================
echo.

echo [1/4] Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no está en el PATH
) else (
    echo [OK] Python
    python --version
)
echo.

echo [2/4] Paquete app...
if exist "app\__main__.py" (echo [OK] app\__main__.py) else (echo [ERROR] falta app)
if exist "config.json" (echo [OK] config.json) else (echo [INFO] Sin config previa)
echo.

echo [3/4] Gemma / LiteRT (guía + traducción IA)...
curl -s http://127.0.0.1:9379/v1/models >nul 2>&1
if %errorlevel% EQU 0 (
    echo [OK] LiteRT en 9379
) else (
    echo [INFO] LiteRT NO detectado — scripts\Setup_Gemma_LiteRT.bat
)
echo.

echo [4/4] Traducción Offline Marian...
if exist "build\offline-en-es\config.json" (
    echo [OK] Modelo offline en build\offline-en-es
) else (
    echo [INFO] Falta modelo — python scripts\prepare_offline_model.py
)
echo.

echo Arranque: Iniciar_EstiloKaio.bat  ^(o: python -m app^)
echo.
pause
