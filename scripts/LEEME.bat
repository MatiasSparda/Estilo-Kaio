@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ========================================
echo    Guía rápida - Estilo Kaio
echo ========================================
echo.
echo Arranque: Iniciar_EstiloKaio.bat
echo.
echo 1. Pestana Captura: región traductor + diario
echo 2. Pestana Guía: cargar .txt o importar URL
echo 3. Pestana Traductor: idiomas + Setup/Iniciar Gemma
echo 4. Guía y traducción Gemma usan el mismo motor LiteRT (sin Ollama)
echo.
echo Atajos (default):
echo   Alt+T  traducir región (bloques OCR separados)
echo   Alt+G  consultar guía
echo.
echo Gemma: scripts\Setup_Gemma_LiteRT.bat
echo Docs:  docs\README.md
echo.
pause
