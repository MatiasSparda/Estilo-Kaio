# Estilo Kaio — traductor OCR + asistente de guía

**Estilo Kaio** es una app de escritorio Windows: traducción instantánea por regiones OCR y asistente de guías con **Gemma (LiteRT)** local. Una sola IA generativa (Gemma) para guía y traducción IA; traducción **Offline** usa Marian EN→ES embebido (no es un LLM).

## Arranque rápido

```bat
Iniciar_EstiloKaio.bat
```

O desde la raíz del repo:

```bat
pip install -r scripts/requirements.txt
python -m app
```

---

## Instalación para usuarios

### Opción 1: Ejecutable (recomendado)

1. GitHub → **Releases** → bajá `EstiloKaio-vX.Y.Z-windows.zip`
2. Extraé y ejecutá `EstiloKaio.exe` (no hace falta Python)
3. Configurá **región del traductor**, **región del diario** (guía) y cargá una guía `.txt` si usás Alt+G

El zip incluye **traducción Offline Marian EN→ES** (~590 MB, local, sin límites). **Gemma** (guía + traducción IA) se configura una vez con **Setup** en la barra superior de la app.

**Llevar el exe a otro PC (solo Offline):** copiá `EstiloKaio.exe` (+ `config.json` opcional). Windows 10/11 64-bit. Sin Python, pip, Ollama ni Gemma. Para **guía** o **traducción Gemma**, hacé Setup Gemma en ese PC.

### Opción 2: Desde código fuente

Ver [Build local](#build-local) más abajo.

---

## Atajos (configurables en pestaña **Atajos**)

| Atajo por defecto | Acción |
|-------------------|--------|
| **Alt+T** | Traducir región del traductor |
| **Alt+G** | Consultar guía (OCR del diario) |
| **Alt+X** | Cerrar overlay de traducción |

Los atajos son **globales** (`RegisterHotKey` en Windows): funcionan con DOSBox/emuladores en foco. Si no responden, el status inferior indica `Hotkeys (globales + respaldo)` o `fallback keyboard` — probá cambiar a **F9** en Atajos.

---

## Traductor

### Motores de traducción

| Modo | Qué hace |
|------|----------|
| **Offline** | Marian EN→ES local, ~1–4 s, sin Gemma |
| **Offline + Gemma** | OCR una vez → borrador Offline ya visible + Gemma en paralelo reemplaza al terminar. En CPU: borrador ~5 s; Gemma 1–3 min o timeout |
| **Gemma** | Solo Gemma (LiteRT) |

Orquestación en `app/translation_pipeline.py` (threads + callbacks; no duplica lógica en la UI).

### Motores OCR

| Motor | Cuándo usarlo |
|-------|----------------|
| **OneOCR** | Diálogos pixel / CRPG (recomendado) |
| **RapidOCR** | Escenas amplias; incluido en el exe |
| **EasyOCR** | Alternativa (instalación aparte) |
| **Windows OCR** | Requiere pack de idioma inglés en Windows |

Fallback automático: si un motor corta el texto, prueba otros y prioriza resultados completos (heurística de frase terminada en `.!?`, sin hardcodear diálogos del juego).

### Vista overlay

| Modo | Comportamiento |
|------|----------------|
| **Layer** | Una ventana con todos los bloques |
| **Over** | Una ventanita por bloque OCR, posicionada sobre el texto original (p. ej. amarillo y blanco del diálogo por separado) |

Cerrar overlay: **Alt+X**, ESC o click derecho (Over).

### Gemma (barra superior)

- **Setup** — descarga/configura LiteRT y modelo
- **Iniciar / Detener** — servidor local (puerto 9379)
- **Backend** — RAM (CPU) o GPU
- Compartido por **traducción Gemma** y **pestaña Guía**

---

## Asistente de guía (Alt+G)

- OCR de la región del **diario** + guía `.txt` o importación por URL
- **Gemma (LiteRT)** — misma IA que traducción Gemma (**Ollama eliminado**, no se usa)
- Pestaña **Guía**: cargar `.txt`, elegir sección (Auto recomendado), preguntar manualmente o con Alt+G

Requiere **Gemma iniciado** (botón Iniciar arriba).

---

## Build local

Artefactos **no se suben al repo** (`build/`, `dist/` están en `.gitignore`). El release oficial lo genera GitHub Actions.

```powershell
cd d:\asistente
pip install -r scripts/requirements.txt
python scripts/prepare_offline_model.py
pyinstaller --noconfirm scripts/EstiloKaio.spec
```

Salida: `dist/EstiloKaio.exe`

---

## Publicar release (GitHub Actions)

El workflow **Release** buildea en Windows, empaqueta el zip y crea el GitHub Release con tag semver.

### Desde la web

1. Subí tus cambios a `main` (`git push origin main`)
2. GitHub → pestaña **Actions**
3. Workflow **Release** (columna izquierda)
4. **Run workflow** (botón arriba a la derecha)
5. Elegí bump: **patch** (fix), **minor** (feature) o **major** (breaking)
6. **Run workflow**
7. Esperá ~10–15 min. Al terminar: **Releases** → nuevo `EstiloKaio-vX.Y.Z-windows.zip`

**Notas del workflow:**

- Si `VERSION` en el repo **aún no tiene tag**, completa esa versión pendiente (ignora el bump elegido)
- Si ya existe tag para `VERSION`, aplica el bump elegido
- Solo commitea `VERSION` + `app/__init__.py`; el exe **no** va al repo, solo al Release

### Desde CLI (`gh`)

```powershell
gh workflow run Release -f bump=patch
# o: minor | major
gh run list --workflow=Release
```

---

## Estructura del repo

| Ruta | Descripción |
|------|-------------|
| `app/` | Código principal |
| `app/translation_pipeline.py` | Orquestación offline / offline+gemma / gemma |
| `app/guide_assistant.py` | Asistente de guía (Gemma) |
| `app/global_hotkeys.py` | Atajos globales Windows |
| `app/legacy/` | Traductores viejos (Argos, online, Ollama installer) — no usados en runtime |
| `scripts/` | `EstiloKaio.spec`, setup Gemma, `prepare_offline_model.py` |
| `tests/` | Tests unitarios |
| `fixtures/ocr/` | Imágenes de prueba OCR |
| `VERSION` | Semver; la Action lo actualiza al publicar |

Config de usuario: `config.json` junto al exe o en `%LOCALAPPDATA%` (sesiones, regiones, atajos, motor OCR/traducción).

---

## Tests

```powershell
$env:PYTHONPATH='.'
python tests/test_ocr_preprocess.py
python tests/test_ocr_dic.py
python tests/test_offline_quality.py
python tests/test_google_translate.py
python tests/test_frozen_boot.py
python tests/test_translation_e2e.py
python tests/test_guide_parser.py
```

---

## Troubleshooting

### Traducción

- **Texto cortado / basura al final** → Motor OCR **OneOCR**; región solo la caja de diálogo (no el marco)
- **Status "OCR incompleto" (naranja)** → RapidOCR cortó; cambiá a OneOCR o achicá la región
- **Gemma timeout (CPU)** → Normal 1–3 min en Offline+Gemma; borrador Offline queda visible
- **Mezcla español+inglés en OCR** → Cerrá overlay (**Alt+X**) antes de capturar

### Hotkeys / UI

- **Atajo no hace nada** → Cerrá otras instancias de EstiloKaio; mirá status (`Hotkeys globales…`); probá F9 en Atajos
- **UI gris vacía (skeleton)** → Exe viejo; reinstalá release reciente

### Guía

- **"Gemma no disponible"** → **Iniciar** en la barra Gemma (no hace falta Ollama)
- **No encuentra sección** → Elegí sección manual en Guía o reformulá con más contexto (lugar, NPC, quest)

### OneOCR

- Usa Snipping Tool de Windows; la primera vez puede descargar DLLs a `%LOCALAPPDATA%\EstiloKaio\oneocr-dlls`

---

## Changelog reciente (resumen)

- Traducción **Offline Marian** (reemplaza Argos/Google/online)
- **Pipeline único** para Offline + Gemma en paralelo
- OCR multi-motor con **fallback** y detección de texto truncado
- **Over**: un overlay por bloque OCR
- **Hotkeys globales** + respaldo keyboard (DOSBox)
- **Guía unificada en Gemma**; Ollama retirado
- Release vía **GitHub Actions**; `dist/`/`build/` fuera del repo
