# Estilo Kaio — traductor OCR + asistente de guía

**Estilo Kaio** es una app de escritorio Windows: traducción instantánea por regiones OCR y asistente de guías con Ollama.

## Arranque

```bat
Iniciar_EstiloKaio.bat
```

O: `python -m app` desde la raíz del repo.

Dependencias: `pip install -r scripts/requirements.txt`

## Instalación y uso

### Opción 1: Ejecutable (Recomendado)

1. En GitHub → **Releases**, bajá el zip `EstiloKaio-vX.Y.Z-windows.zip`
2. Extraé y ejecutá `EstiloKaio.exe` (no hace falta Python)
3. Primera configuración: región del traductor, región del diario, guía `.txt`

Para publicar una release nueva (maintainers): Actions → **Release** → Run workflow → elegí `patch` / `minor` / `major`.

### Opción 2: Desde el código fuente

1. Instalar dependencias: `pip install -r scripts/requirements.txt`
2. Ejecutar: `Iniciar_EstiloKaio.bat` o `python -m app`

## Características

### Traductor (Alt+T)
- Captura región → OCR → motor a elegir:
  - **Gemma (IA local)** — offline
  - **Google Translate** — online
  - **Google + Gemma** — borrador Google + revisión local
- Setup Gemma (opcional): `scripts\Setup_Gemma_LiteRT.bat`

### Asistente de guía (Alt+G)
- OCR del diario + guía `.txt` / import URL
- Ollama local (pestaña Guía)

## Estructura

- `Iniciar_EstiloKaio.bat` — launcher
- `app/` — código
- `scripts/` — setup Gemma, VERIFICAR, packaging (`EstiloKaio.spec`)
- `tests/`, `docs/`, `guias/`, `fixtures/`
- `VERSION` — semver (bumpeado por la Action de release)

## OCR

Si el texto no se lee bien: Windows → Idioma → instalar OCR del idioma del juego.
