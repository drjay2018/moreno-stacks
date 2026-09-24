# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Buscar la DB template en varias ubicaciones posibles
db_template = None
possible_db_paths = [
    os.path.join('..', 'dlab-data', 'data', 'dlab.db'),
    os.path.join('dlab-data', 'data', 'dlab.db'),
    os.path.join('data', 'dlab.db'),
]
for p in possible_db_paths:
    if os.path.exists(p):
        db_template = p
        break

# Construir datas dinamicamente
datas = [
    ('app/templates', 'app/templates'),
    ('app/static', 'app/static'),
    ('db_schema.sql', '.'),
]
if os.path.exists('powerbi'):
    datas.append(('powerbi', 'powerbi'))
if db_template:
    datas.append((db_template, 'dlab-data/data'))

a = Analysis(
    ['app_tray.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'pyarrow',
        'sqlite3',
        'flask',
        'sqlalchemy',
        'flask_wtf',
        'flask_sqlalchemy',
        'cryptography',
        'cryptography.fernet',
        'pystray',
        'PIL',
        'google.oauth2.credentials',
        'google.auth.transport.requests',
        'googleapiclient.discovery',
    ],
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
    [],
    exclude_binaries=True,
    name='DLAB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='DLAB',
)
