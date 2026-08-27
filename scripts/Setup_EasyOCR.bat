@echo off
setlocal
cd /d "%~dp0.."
echo Instalando EasyOCR (CPU)...
python -m pip install --upgrade -r scripts\requirements-ocr.txt
if errorlevel 1 (
  echo ERROR: pip install fallo
  exit /b 1
)
echo Calentando modelos en ingles...
set PYTHONPATH=%CD%
python -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False); print('EasyOCR OK')"
if errorlevel 1 (
  echo ERROR: warmup EasyOCR fallo
  exit /b 1
)
echo Listo.
exit /b 0
