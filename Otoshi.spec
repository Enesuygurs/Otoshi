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
    # pynput picks its backend at runtime.
    hiddenimports=['pynput.keyboard._win32', 'pynput.mouse._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'keyboard', 'tkinter', 'customtkinter', 'pystray',
              'ssl', '_ssl', '_hashlib', 'PySide6.QtNetwork', 'PySide6.QtSvg'],
    noarchive=False,
    optimize=0,
)

# Parts of Qt and Pillow that Otoshi never uses (about 45 MB).
_DROP = (
    'opengl32sw.dll',  # software OpenGL fallback; plain widgets never use OpenGL (20 MB)
    'pyside6/translations/',  # Qt's own UI translations; Otoshi ships its own strings
    'qt6network', 'qt6svg', 'plugins/tls/', 'plugins/networkinformation/', 'plugins/iconengines/',
    'plugins/generic/', 'plugins/styles/',  # the Fusion style is built in
    'qdirect2d', 'qminimal', 'qoffscreen',  # only the qwindows platform plugin is needed
    'qgif', 'qicns', 'qjpeg', 'qsvg', 'qtga', 'qtiff', 'qwbmp', 'qwebp',  # PNG is built in, ICO stays
    'libcrypto', 'libssl',  # OpenSSL: no network access
    'pil/_avif', 'pil/_webp', 'pil/_imagingcms', 'pil/_imagingtk', 'pil/_imagingmath',
)


def _keep(entry):
    name = entry[0].replace('\\', '/').lower()
    return not any(token in name for token in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
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
