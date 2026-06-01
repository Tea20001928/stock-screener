# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('auto_picker/__init__.py', 'auto_picker'), ('C:/Users/25377/AppData/Local/Programs/Python/Python311/Lib/site-packages/akshare/file_fold/calendar.json', 'akshare/file_fold'), ('C:/Users/25377/AppData/Local/Programs/Python/Python311/Lib/site-packages/py_mini_racer/mini_racer.dll', 'py_mini_racer'), ('C:/Users/25377/AppData/Local/Programs/Python/Python311/Lib/site-packages/py_mini_racer/icudtl.dat', 'py_mini_racer')],
    hiddenimports=['config', 'data_fetcher', 'screener', 'excel_writer', 'main', 'auto_picker', 'auto_picker.config', 'auto_picker.data_fetcher', 'auto_picker.screener', 'auto_picker.excel_writer', 'auto_picker.main', 'akshare', 'openpyxl', 'pandas', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='stock-screener',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
