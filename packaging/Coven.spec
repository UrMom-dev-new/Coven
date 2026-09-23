# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent

hiddenimports = ["clr"] + collect_submodules("webview.platforms")

datas = [
    (str(ROOT / "public"), "public"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "packaging" / "voice"), "packaging/voice"),
    (str(ROOT / "docs" / "product-contract.md"), "docs"),
    (str(ROOT / "README.md"), "."),
]

a = Analysis(
    [str(ROOT / "coven" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "pyinstaller_runtime_hook.py")],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Coven",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    version=str(ROOT / "packaging" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Coven",
)
