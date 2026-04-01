# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas_pysqlcipher = []
try:
    datas_pysqlcipher = collect_data_files("pysqlcipher3")
except Exception:
    pass

a = Analysis(
    ["quick_export.py"],
    pathex=[],
    binaries=[],
    datas=datas_pysqlcipher,
    hiddenimports=[
        "pysqlcipher3",
        "pysqlcipher3.dbapi2",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "pandas",
        "PIL", "cv2", "scipy",
        "docx", "lxml",
    ],
    win_no_prefer_redirects=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="WeChat2Word_Quick",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False,
    name="WeChat2Word_Quick",
)
