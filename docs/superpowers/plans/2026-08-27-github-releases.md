# GitHub Releases Implementation Plan

**Goal:** Releases Windows vía Action manual (`workflow_dispatch` + auto bump).

**Status:** Implementado — `.github/workflows/release.yml`, `VERSION`, `scripts/EstiloKaio.spec`.

## Uso

1. Push a `main` en GitHub
2. Actions → **Release** → Run workflow
3. Elegí `patch` / `minor` / `major`
4. Esperá el job Windows; el release queda publicado con el zip
