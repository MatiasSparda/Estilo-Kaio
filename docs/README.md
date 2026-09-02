# Estilo Kaio — traductor OCR + asistente de guía

**Estilo Kaio** es una app de escritorio Windows: traducción instantánea por regiones OCR y asistente de guías con **Gemma (LiteRT)** local.

## Arranque

```bat
Iniciar_EstiloKaio.bat
```

O: `python -m app` desde la raíz del repo.

Dependencias: `pip install -r scripts/requirements.txt`

## Instalación y uso

### Opción 1: Ejecutable (Recomendado)

1. En GitHub → **Releases**, bajá el zip `EstiloKaio-vX.Y.Z-windows.zip`
2. Extraé y ejecutá `EstiloKaio.exe` (no hace falta Python ni pip)
3. Primera configuración: región del traductor, región del diario, guía `.txt`

El zip trae **traducción Offline Marian EN→ES** (local, sin límites). **Gemma** (guía + traducción IA) se configura aparte con Setup en la app.

Para publicar una release nueva (maintainers): Actions → **Release** → Run workflow → elegí `patch` / `minor` / `major`.

### Opción 2: Desde el código fuente

1. Instalar dependencias: `pip install -r scripts/requirements.txt`
2. Ejecutar: `Iniciar_EstiloKaio.bat` o `python -m app`

## Características

### Traductor (Alt+T)
- Captura región → OCR → motor a elegir:
  - **Offline** — Marian local, sin límites
  - **Offline + Gemma** — borrador offline + revisión local
  - **Gemma (IA local)** — offline, setup aparte
- Setup Gemma (opcional): `scripts\Setup_Gemma_LiteRT.bat`

### Asistente de guía (Alt+G)
- OCR del diario + guía `.txt` / import URL
- **Gemma (LiteRT)** local — misma IA que traducción con Gemma (sin Ollama)

## Estructura

- `Iniciar_EstiloKaio.bat` — launcher
- `app/` — código
- `scripts/` — setup Gemma, VERIFICAR, packaging (`EstiloKaio.spec`)
- `tests/`, `docs/`, `guias/`, `fixtures/`
- `VERSION` — semver (bumpeado por la Action de release)

## OCR

Si el texto de juego (fuente pixel) se lee mal: motor **OneOCR** para diálogos pixel; **RapidOCR** para escenas amplias. Recortá solo el texto, no el marco. Windows OCR pide pack de idioma inglés (Configuración → Hora e idioma → Idioma).

## Troubleshooting traducción

- **Texto cortado / basura al final**: Motor OCR → OneOCR. Región solo caja de diálogo.
- **Gemma timeout (CPU)**: Normal 1–3 min. Usá modo Offline solo. Borrador offline queda visible.
- **UI gris vacía**: Reinstalar exe reciente. Hotkeys globales requieren exe post-fix.
- **DOSBox no responde Alt+5**: Atajos → F9 o Pause. Ver "Hotkeys globales" en status.
- **Mezcla español+inglés**: Cerrar overlay (Alt+X) antes de capturar.
