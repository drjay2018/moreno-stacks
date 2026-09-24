import sys
import os
import zipfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# Configuración
APP_NAME = "DLAB CRM Inmobiliaria"
DEST_FOLDER_NAME = "DLAB_CRM"
EXE_NAME = "DLAB.exe"
ZIP_NAME = "dlab_app.zip"
ICON_NAME = "dlab_icon.ico"

def get_base_path():
    """Obtener la ruta base, ya sea en modo desarrollo o compilado por PyInstaller."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

class InstaladorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Instalador - {APP_NAME}")
        self.root.geometry("500x350")
        self.root.resizable(False, False)
        
        # Centrar ventana
        self.root.eval('tk::PlaceWindow . center')
        
        # Establecer icono si existe
        icon_path = os.path.join(get_base_path(), ICON_NAME)
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass

        # Estilo moderno básico
        style = ttk.Style()
        style.theme_use('clam')
        
        self.setup_ui()
        
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = ttk.Label(main_frame, text=f"Instalando {APP_NAME}", font=("Arial", 16, "bold"))
        title_label.pack(pady=(10, 20))
        
        # Descripción
        desc_label = ttk.Label(main_frame, text="Por favor, espera mientras se extraen los archivos del sistema\ny se configuran los accesos directos en tu computadora.", justify=tk.CENTER)
        desc_label.pack(pady=(0, 30))
        
        # Etiqueta de estado
        self.status_label = ttk.Label(main_frame, text="Listo para instalar...", font=("Arial", 10))
        self.status_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Barra de progreso
        self.progress = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, length=460, mode='determinate')
        self.progress.pack(pady=(0, 30))
        
        # Botón Instalar
        self.install_btn = ttk.Button(main_frame, text="Comenzar Instalación", command=self.start_installation)
        self.install_btn.pack(ipadx=20, ipady=5)

    def start_installation(self):
        self.install_btn.config(state=tk.DISABLED)
        self.progress['value'] = 0
        
        # Ejecutar en hilo separado para no bloquear la UI
        threading.Thread(target=self.install_process, daemon=True).start()

    def update_status(self, text, progress_val=None):
        self.status_label.config(text=text)
        if progress_val is not None:
            self.progress['value'] = progress_val
        self.root.update_idletasks()

    def create_shortcut(self, target_exe, icon_path, working_dir):
        """Crea un acceso directo en el Escritorio usando PowerShell."""
        ps_script = f'''
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path -Path $DesktopPath -ChildPath "{APP_NAME}.lnk"
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "{target_exe}"
$Shortcut.IconLocation = "{icon_path}"
$Shortcut.WorkingDirectory = "{working_dir}"
$Shortcut.Save()
'''
        try:
            subprocess.run(["powershell", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            print(f"Error creando acceso directo: {e}")
            return False

    def install_process(self):
        try:
            base_path = get_base_path()
            zip_path = os.path.join(base_path, ZIP_NAME)
            
            if not os.path.exists(zip_path):
                self.root.after(0, lambda: messagebox.showerror("Error", "No se encontró el archivo de datos (zip)."))
                self.root.after(0, lambda: self.install_btn.config(state=tk.NORMAL))
                return

            dest_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), DEST_FOLDER_NAME)
            
            # Crear directorio destino
            self.update_status("Preparando directorio de instalación...", 5)
            os.makedirs(dest_dir, exist_ok=True)
            
            # Extraer ZIP
            self.update_status("Extrayendo archivos del sistema (esto puede tomar un par de minutos)...", 10)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                total_files = len(zip_ref.namelist())
                extracted = 0
                
                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, dest_dir)
                    extracted += 1
                    # Actualizar progreso (del 10% al 90%)
                    prog = 10 + (extracted / total_files * 80)
                    if extracted % 50 == 0:  # No actualizar UI en cada archivo pequeño
                        self.root.after(0, self.update_status, f"Extrayendo: {file_info.filename[:40]}...", prog)

            self.update_status("Configurando accesos directos...", 90)
            
            # Archivos finales
            target_exe = os.path.join(dest_dir, EXE_NAME)
            icon_path = os.path.join(dest_dir, ICON_NAME) # Copiaremos el icono ahí
            
            # Extraer icono si está en el MEIPASS al destino
            source_icon = os.path.join(base_path, ICON_NAME)
            if os.path.exists(source_icon):
                import shutil
                shutil.copy2(source_icon, icon_path)
            else:
                icon_path = target_exe # Fallback: usar icono del exe si no hay .ico externo
            
            # Crear acceso directo
            self.create_shortcut(target_exe, icon_path, dest_dir)
            
            self.update_status("¡Instalación completada con éxito!", 100)
            
            self.root.after(0, self.finish_installation)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error Fatal", f"Ocurrió un error durante la instalación:\n{str(e)}"))
            self.root.after(0, lambda: self.install_btn.config(state=tk.NORMAL))

    def finish_installation(self):
        messagebox.showinfo("¡Éxito!", f"El sistema {APP_NAME} se ha instalado correctamente.\n\nPuedes abrirlo desde el acceso directo creado en tu Escritorio.")
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = InstaladorApp(root)
    root.mainloop()
