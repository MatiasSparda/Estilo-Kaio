# -*- mode: python ; coding: utf-8 -*-
# Desde la raiz del repo:
#   python scripts/prepare_offline_model.py
#   pyinstaller --noconfirm scripts/EstiloKaio.spec

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))
entrypoint = os.path.join(repo_root, "app", "__main__.py")
offline_model = os.path.join(repo_root, "build", "offline-en-es")

if not os.path.isdir(offline_model) or not os.listdir(offline_model):
    raise SystemExit(
        "Falta build/offline-en-es. Corre: python scripts/prepare_offline_model.py"
    )

datas = [(offline_model, "offline-en-es")]
binaries = []
hiddenimports = [
    "customtkinter",
    "PIL._tkinter_finder",
    "winrt.windows.media.ocr",
    "winrt.windows.graphics.imaging",
    "winrt.windows.storage.streams",
    "winrt.windows.globalization",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "keyboard",
    "mss",
    "requests",
    "bs4",
    "app",
    "app.guide_importer",
    "app.guide_parser",
    "app.ui_theme",
    "app.proper_nouns",
    "app.gemma_translate",
    "app.global_hotkeys",
    "app.translation_pipeline",
    "app.translator",
    "app.ocr_engine",
    "app.screen_capture",
    "app.guide_assistant",
    "app.ollama_assistant",
    "app.region_selector",
    "app.main",
    "app.offline_translate",
    "app.offline_worker",
    "app.ocr_backends.rapidocr_backend",
    "transformers",
    "sentencepiece",
]

for pkg_name in (
    "transformers",
    "sentencepiece",
    "rapidocr",
    "onnxruntime",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [entrypoint],
    pathex=[repo_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="EstiloKaio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
