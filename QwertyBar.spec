# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the portable Qwerty Bar client."""

from pathlib import Path

root = Path(SPECPATH)

datas = [(str(root / "LICENSE"), ".")]
catalog = root / "data" / "catalog.json"
if catalog.exists():
    datas.append((str(catalog), "data"))

dicts_dir = root / "data" / "dicts"
if dicts_dir.exists():
    for path in sorted(dicts_dir.glob("*.json")):
        datas.append((str(path), "data/dicts"))

custom_dir = root / "custom_dicts"
if custom_dir.exists():
    datas.append((str(custom_dir), "custom_dicts"))

sounds = root / "assets" / "sounds"
if sounds.exists():
    datas.append((str(sounds), "assets/sounds"))

a = Analysis(
    [str(root / "run.pyw")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["fetch_dicts", "qwerty_bar", "qwerty_bar.paths"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QwertyBar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="QwertyBar",
)
