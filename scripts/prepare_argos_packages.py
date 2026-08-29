"""Descarga el par Argos en-es a build/argos-packages (CI y build local)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "build" / "argos-packages"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGES_DIR"] = str(DEST)
    os.environ["ARGOS_DEVICE_TYPE"] = "cpu"

    import argostranslate.package as pkg

    pkg.update_package_index()
    available = pkg.get_available_packages()

    for item in available:
        if getattr(item, "type", "") != "sbd":
            continue
        from_codes = getattr(item, "from_codes", None) or []
        if from_codes and "en" not in from_codes:
            continue
        path = item.download()
        pkg.install_from_path(path)
        print(f"Argos sbd: {getattr(item, 'from_code', '')} {item.type}")

    pair = next(
        (p for p in available if p.from_code == "en" and p.to_code == "es"),
        None,
    )
    if pair is None:
        print("Argos: no hay paquete en-es en el índice.", file=sys.stderr)
        return 1
    path = pair.download()
    pkg.install_from_path(path)
    print(f"Argos en-es instalado en {DEST}")

    if not any(DEST.iterdir()):
        print(f"Argos: {DEST} quedó vacío.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
