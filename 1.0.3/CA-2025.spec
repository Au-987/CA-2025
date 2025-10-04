# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 导入必要的模块
import os

a = Analysis(['Camera Assistant-0.2.py'],
             pathex=['d:\\jxc\\Py\\Programme\\software\\CA-2025'],
             binaries=[],
             datas=[('CA-2025.ico', '.'), ('splash.png', '.')],
             hiddenimports=['PIL._tkinter_finder'],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=['IPython', 'jupyter_client', 'jupyter_core', 'matplotlib', 'numpy', 'scipy'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='CA-2025',
          debug=False,
          bootloader_ignore_signals=False,
          strip=True,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          icon='CA-2025.ico')