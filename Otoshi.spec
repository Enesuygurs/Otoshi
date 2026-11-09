# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller Otoshi.spec  ->  dist/Otoshi/Otoshi.exe
#
# One-folder build without UPX: starts faster than a one-file exe (nothing is
# unpacked to %TEMP% on every launch) and is flagged far less often by
# antivirus heuristics, which dislike self-extracting, UPX-packed Python apps.

import re

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

with open('otoshi/__init__.py', encoding='utf-8') as f:
    VERSION = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)
_numbers = tuple(int(p) for p in VERSION.split('.')[:4])
_numbers += (0,) * (4 - len(_numbers))

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_numbers, prodvers=_numbers),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [
                StringStruct('CompanyName', 'Enes Uygur'),
                StringStruct('FileDescription', 'Otoshi - macro recorder and auto clicker'),
                StringStruct('FileVersion', VERSION),
                StringStruct('InternalName', 'Otoshi'),
                StringStruct('LegalCopyright', 'MIT License'),
                StringStruct('OriginalFilename', 'Otoshi.exe'),
                StringStruct('ProductName', 'Otoshi'),
                StringStruct('ProductVersion', VERSION),
            ])
        ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('otoshi/assets', 'otoshi/assets'), ('otoshi/locales', 'otoshi/locales')],
    # pynput and pystray pick their backend at runtime.
    hiddenimports=['pynput.keyboard._win32', 'pynput.mouse._win32', 'pystray._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'keyboard'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Otoshi',
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
    icon='otoshi/assets/icon.ico',
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Otoshi',
)
