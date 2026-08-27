# Estilo Kaio — GitHub Releases (build via Action)

Fecha: 2026-08-27  
Estado: aprobado

## Objetivo

Publicar releases de Windows desde GitHub Actions, disparadas a mano. El repo guarda solo código; el EXE se genera en CI y se adjunta al release.

## Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Contenido del repo | Solo código (no binarios commitados de release) |
| Trigger | `workflow_dispatch` (el usuario corre la Action) |
| Versionado | Auto bump `patch` / `minor` / `major` |
| Persistencia | Commit del bump en `main` + tag `vX.Y.Z` |
| Publicación | Release **publicado** al terminar el build (no draft) |
| Enfoque CI | Un solo workflow |

## Fuera de alcance

- Empaquetar modelos Gemma / LiteRT
- Empaquetar Ollama
- Firma de código / notarización
- Builds macOS / Linux
- Releases draft o pre-release

## Flujo

```
Usuario → Actions → "Release" → input bump
  → leer VERSION
  → calcular X.Y.Z
  → escribir VERSION + app/__init__.__version__
  → commit + push main
  → tag vX.Y.Z + push
  → setup Python 3.11 (windows-latest)
  → pip install -r scripts/requirements.txt
  → pyinstaller --noconfirm scripts/EstiloKaio.spec
  → zip dist/EstiloKaio.exe → EstiloKaio-vX.Y.Z-windows.zip
  → gh release create (published) + asset zip
```

## Versionado

- Archivo raíz `VERSION`: semver sin prefijo `v`. Inicial: `1.0.0`.
- Primer release vía CI con `patch` → `1.0.1` (siempre bumpea antes de publicar).
- `app/__init__.py` mantiene `__version__` sincronizado en el mismo commit.
- Tag Git: `v` + VERSION. Commit: `chore: release vX.Y.Z`.
- Si el tag ya existe, el workflow falla.

## Workflow

Archivo: `.github/workflows/release.yml`

- Trigger: solo `workflow_dispatch` con input `bump`
- Runner: `windows-latest`, Python 3.11
- Permisos: `contents: write`
- Concurrency: group `release`, `cancel-in-progress: false`
- Asset zip: solo `EstiloKaio.exe`

## Criterios de éxito

1. Actions → Release → Run workflow → `patch` termina OK
2. `main` tiene commit de release y `VERSION` actualizado
3. Existe tag `vX.Y.Z` y Release publicado con el zip
4. El EXE arranca en Windows sin Python
