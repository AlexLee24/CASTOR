# -*- mode: python ; coding: utf-8 -*-
import os

# 把 src 加入模組搜尋路徑
pathex = [os.path.abspath('src')]

# 靜態檔案打包 (不再需要煩惱 Windows 或 Mac 的符號差異)
datas = [
    ('src/castorGUI/frontend', 'frontend'),
    ('src/castorGUI/data', 'data'),
]

# 你想排除的「垃圾」模組全部寫在這裡，想加幾個就加幾個
#
# astropy.visualization pulls in matplotlib at import time (wcsaxes/__init__.py
# calls pytest.importorskip("matplotlib") itself), and CASTOR only ever touches
# astropy.time / astropy.coordinates / astropy.units — so it goes too, along
# with everything matplotlib alone was dragging in (Pillow, fonttools, ...).
excludes = [
    'pytest',
    'matplotlib',
    'astropy.visualization',
    'tkinter',
    'IPython',
    'notebook'
]

a = Analysis(
    ['src/castorGUI/desktop.py'],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=[],
    # Shadows pyinstaller-hooks-contrib's hook-astropy.py, which crashes the
    # whole build over one submodule needing matplotlib — see the docstring
    # in pyinstaller_hooks/hook-astropy.py.
    hookspath=['pyinstaller_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CASTOR-ETC', # 輸出的執行檔名稱
    icon='assets/desktop/castor.ico', # Windows 執行檔圖示
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 這個就是原本的 --noconsole
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='CASTOR-ETC.app',
    icon='assets/desktop/castor.icns',
    bundle_identifier=None,
)