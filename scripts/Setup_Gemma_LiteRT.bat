@echo off
chcp 65001 >nul
echo ========================================
echo  Setup Gemma 4 E4B (LiteRT-LM offline)
echo  Traduccion + Guia — un solo modelo
echo ========================================
echo.
echo 1) pip install litert-lm
echo 2) borrar gemma4-e2b si existe
echo 3) import gemma4-e4b (~3.7 GB, internet UNA vez)
echo.
python -m pip install --upgrade "litert-lm>=0.16.0"
if errorlevel 1 (
  echo ERROR: falló pip install litert-lm
  pause
  exit /b 1
)
echo.
echo Borrando modelos viejos...
litert-lm delete gemma4-e2b 2>nul
echo.
echo Importando Gemma 4 E4B (puede tardar varios minutos)...
litert-lm import --from-huggingface-repo litert-community/gemma-4-E4B-it-litert-lm gemma-4-E4B-it.litertlm gemma4-e4b
if errorlevel 1 (
  echo ERROR: falló el import. Revisá espacio en disco (~5 GB libres) y red.
  pause
  exit /b 1
)
echo.
echo OK. Modelo gemma4-e4b listo.
echo En la app: elegí Memoria IA = RAM ^(CPU^) o VRAM ^(GPU^), luego Iniciar.
pause
