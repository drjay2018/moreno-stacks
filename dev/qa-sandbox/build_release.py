import os
import shutil
import zipfile
import subprocess
from pathlib import Path

def print_step(msg):
    print("\n" + "="*60)
    print(f"PASO: {msg}")
    print("="*60 + "\n")

def run_command(cmd, cwd=None):
    print(f"Ejecutando: {cmd}")
    result = subprocess.run(cmd, cwd=cwd, shell=True)
    if result.returncode != 0:
        print(f"Error ejecutando comando. Codigo de salida: {result.returncode}")
        sys.exit(1)

def zip_directory(folder_path, zip_path):
    print_step(f"Comprimiendo {folder_path} en {zip_path}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname)

if __name__ == "__main__":
    import sys
    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DIST_DIR = os.path.join(BASE_DIR, "dist")
    APP_DIR = os.path.join(DIST_DIR, "DLAB")
    ZIP_PATH = os.path.join(DIST_DIR, "dlab_app.zip")
    INSTALLER_SPEC = "build_installer.spec"
    
    # 1. Compilar aplicación principal
    print_step("Paso 1: Compilando aplicación principal (DLAB)")
    pyinstaller_exe = os.path.join(BASE_DIR, ".venv", "Scripts", "pyinstaller.exe")
    run_command(f'"{pyinstaller_exe}" build_app.spec --clean -y')

    # 1.1 Compilar actualizador auxiliar y colocarlo junto a DLAB.exe
    #     (debe quedar DENTRO del ZIP para llegar a instalaciones nuevas y updates)
    print_step("Paso 1.1: Compilando actualizador auxiliar (updater.exe)")
    run_command(f'"{pyinstaller_exe}" build_updater.spec --clean -y')
    updater_src = os.path.join(DIST_DIR, "updater.exe")
    updater_dst = os.path.join(APP_DIR, "updater.exe")
    if os.path.exists(updater_src):
        shutil.copy2(updater_src, updater_dst)
        print(f"updater.exe copiado a {updater_dst}")
    else:
        print(f"ADVERTENCIA: no se encontro {updater_src}; el auto-update no funcionara.")
    
    # 2. Copiar carpeta powerbi a la raiz para que esté junto al .exe y no oculta en _internal
    powerbi_src = os.path.join(BASE_DIR, "powerbi")
    powerbi_dst = os.path.join(APP_DIR, "powerbi")
    if os.path.exists(powerbi_src):
        if os.path.exists(powerbi_dst):
            shutil.rmtree(powerbi_dst)
        shutil.copytree(powerbi_src, powerbi_dst)
        print(f"Carpeta powerbi copiada a {powerbi_dst}")

    # 3. Comprimir en ZIP
    if not os.path.exists(APP_DIR):
        print(f"Error: No se encontro la carpeta compilada {APP_DIR}")
        sys.exit(1)
        
    zip_directory(APP_DIR, ZIP_PATH)
    
    # 3. Asegurar que tenemos el icono en formato .ico
    print_step("Paso 2: Asegurar formato de ícono (.ico)")
    png_icon = os.path.join(BASE_DIR, "app", "static", "img", "dlab_favicon.png")
    ico_icon = os.path.join(BASE_DIR, "dlab_icon.ico")
    
    # Usaremos Pillow si está instalado para convertirlo
    try:
        from PIL import Image
        if os.path.exists(png_icon) and not os.path.exists(ico_icon):
            img = Image.open(png_icon)
            img.save(ico_icon, format='ICO')
            print(f"Icono creado en {ico_icon}")
    except ImportError:
        print("Pillow no esta instalado, pero no es critico si el icono ya existe o no se usa.")

    # 4. Compilar el Instalador
    print_step("Paso 3: Compilando el Instalador_DLAB.exe")
    
    # Determinar datas
    datas_str = f"        ('{ZIP_PATH.replace(chr(92), '/')}', '.')"
    if os.path.exists(ico_icon):
        datas_str += f",\n        ('{ico_icon.replace(chr(92), '/')}', '.')"
        
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[
{datas_str}
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
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
    icon=r'{ico_icon}' if os.path.exists(r'{ico_icon}') else None
)
"""
    with open(os.path.join(BASE_DIR, INSTALLER_SPEC), "w", encoding="utf-8") as f:
        f.write(spec_content)
        
    run_command(f'"{pyinstaller_exe}" {INSTALLER_SPEC} --clean -y')
    
    # 5. Generar checksums SHA256
    print_step("Paso 4: Generando checksums SHA256")
    import hashlib
    
    checksums = []
    for artifact_name in ["dlab_app.zip", "Instalador_DLAB.exe"]:
        artifact_path = os.path.join(DIST_DIR, artifact_name)
        if os.path.exists(artifact_path):
            h = hashlib.sha256()
            with open(artifact_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            checksum = h.hexdigest()
            checksums.append(f"{checksum}  {artifact_name}")
            print(f"  {artifact_name}: {checksum}")
    
    checksum_path = os.path.join(DIST_DIR, "checksum.txt")
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("\n".join(checksums))
    print(f"Checksums guardados en: {checksum_path}")
    
    print_step("Proceso Completado con Exito!")
    print(f"Archivos generados en: {DIST_DIR}")
    print(f"  - Instalador_DLAB.exe (instalador completo)")
    print(f"  - dlab_app.zip (para auto-update)")
    print(f"  - checksum.txt (verificacion de integridad)")
