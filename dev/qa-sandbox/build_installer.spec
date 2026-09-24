# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('H:/Mi unidad/Proyecto - CRM Inmobiliaria/dlab-app/dist/dlab_app.zip', '.'),
        ('H:/Mi unidad/Proyecto - CRM Inmobiliaria/dlab-app/dlab_icon.ico', '.')
    ],
    hiddenimports=[],
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
    name='Instalador_DLAB',
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
    icon=r'H:\Mi unidad\Proyecto - CRM Inmobiliaria\dlab-app\dlab_icon.ico' if os.path.exists(r'H:\Mi unidad\Proyecto - CRM Inmobiliaria\dlab-app\dlab_icon.ico') else None
)
