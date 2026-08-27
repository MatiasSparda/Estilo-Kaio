@echo off
chcp 65001 >nul
echo Deteniendo LiteRT-LM...
taskkill /F /IM litert-lm.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq EstiloKaio-LiteRT*" >nul 2>&1
echo Listo.
timeout /t 1 >nul
