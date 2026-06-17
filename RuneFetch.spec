# -*- mode: python ; coding: utf-8 -*-
"""
RuneFetch — PyInstaller one-file EXE spec.

Build on Windows:
    pip install pyinstaller
    pyinstaller RuneFetch.spec

Output: dist\RuneFetch.exe
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden = [
    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    # yt-dlp
    'yt_dlp',
    'yt_dlp.extractor',
    'yt_dlp.extractor._extractors',
    # HTTP / networking
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    # WebSocket bridge
    'websockets',
    'websockets.server',
    'websockets.legacy',
    'websockets.legacy.server',
    'asyncio',
    # Windows-specific (needed by setup_wizard)
    'winreg',
    'ctypes',
    'ctypes.windll',
    'zipfile',
    'urllib.request',
    # stdlib
    'queue', 'threading', 'dataclasses', 'json',
    're', 'subprocess', 'uuid', 'math', 'time',
    'pathlib', 'shutil', 'hashlib', 'tempfile',
    'secrets', 'ipaddress', 'socket', 'logging',
    'concurrent.futures',
]
hidden += collect_submodules('yt_dlp')
hidden += collect_submodules('PyQt6')
hidden += collect_submodules('websockets')

datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('certifi')
try:
    import PyQt6
    qt_base = os.path.join(os.path.dirname(PyQt6.__file__), 'Qt6')
    if os.path.isdir(qt_base):
        datas += [(qt_base, 'PyQt6/Qt6')]
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'tkinter', 'wx', 'gtk',
        'IPython', 'jupyter', 'notebook',
        'setuptools', 'test', 'unittest',
    ],
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
    name='RuneFetch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
        'PyQt6.QtCore.pyd', 'PyQt6.QtGui.pyd', 'PyQt6.QtWidgets.pyd',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,     # swap with 'assets/icon.ico' if you add one
    uac_admin=False,
    uac_uiaccess=False,
)
