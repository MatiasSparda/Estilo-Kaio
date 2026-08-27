# -*- mode: python ; coding: utf-8 -*-
# Ejecutar desde la raíz del repo:
#   pyinstaller --noconfirm scripts/EstiloKaio.spec

block_cipher = None

a = Analysis(
    ['app/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'winrt.windows.media.ocr',
        'winrt.windows.graphics.imaging',
        'winrt.windows.storage.streams',
        'winrt.windows.globalization',
        'winrt.windows.foundation',
        'winrt.windows.foundation.collections',
        'keyboard',
        'mss',
        'requests',
        'bs4',
        'app',
        'app.guide_importer',
        'app.guide_parser',
        'app.ui_theme',
        'app.proper_nouns',
        'app.gemma_translate',
        'app.translator',
        'app.ocr_engine',
        'app.screen_capture',
        'app.ollama_assistant',
        'app.region_selector',
        'app.main',
    ],
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
    name='EstiloKaio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
