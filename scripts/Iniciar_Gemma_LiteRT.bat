@echo off
chcp 65001 >nul
echo Iniciando LiteRT-LM (Gemma) en http://127.0.0.1:9379 ...
where litert-lm >nul 2>&1
if errorlevel 1 (
  echo No encontré litert-lm. Ejecutá Setup_Gemma_LiteRT.bat primero.
  pause
  exit /b 1
)
start "EstiloKaio-LiteRT" /MIN litert-lm serve --host 127.0.0.1 --port 9379
echo Servidor lanzado en segundo plano. Podés cerrar esta ventana.
timeout /t 2 >nul
