# Guia de Instalacion Local - DLAB CRM Inmobiliaria

## Requisitos previos

- Python 3.10 o superior ([descargar](https://www.python.org/downloads/))
- Git (opcional, solo si clonas el repo)
- Windows 10/11

---

## Paso 1: Clonar o descargar el codigo

```bash
git clone <url-del-repo>
cd Proyecto - CRM Inmobiliaria
```

O descarga el ZIP desde GitHub y extrae la carpeta.

---

## Paso 2: Crear entorno virtual

Desde la carpeta `dlab-app`:

```bash
cd dlab-app
python -m venv .venv
```

Activar el entorno:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat
```

> Si PowerShell bloquea la activacion, ejecuta primero:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## Paso 3: Instalar dependencias

```bash
pip install -r requirements.txt
```

Para compilar el `.exe` (opcional):

```bash
pip install pyinstaller pillow
```

---

## Paso 4: Configurar variables de entorno

```bash
copy .env.example .env
```

Editar `.env` con un editor de texto y definir al menos:

```
SECRET_KEY=tu-clave-secreta-aqui
```

Generar una clave segura:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Paso 5: Ejecutar la aplicacion

```bash
python run_local.py
```

La app se abre automaticamente en `http://127.0.0.1:5000`

**Usuario por defecto:** `admin`
**Contrasena:** se imprime en consola la primera vez (guardarla). Despues pedira cambiarla.

---

## Paso 6 (Opcional): Compilar como .exe

```bash
pyinstaller build_app.spec --clean -y
```

El ejecutable queda en `dist/DLAB/DLAB.exe`.

Para generar el instalador:

```bash
python build_release.py
```

Esto genera en `dist/`:
- `Instalador_DLAB.exe` — instalador completo
- `dlab_app.zip` — para auto-update
- `checksum.txt` — verificacion de integridad

---

## Estructura de carpetas importante

```
dlab-app/
├── .env                  # Configuracion (NO subir a git)
├── run_local.py          # Punto de entrada
├── build_app.spec        # Config de PyInstaller
├── build_release.py      # Script de build completo
├── app/                  # Codigo de la aplicacion
├── tests/                # Tests
├── migrations/           # Migraciones de BD
└── dist/                 # Archivos compilados (generados)
```

La base de datos se guarda en: `%APPDATA%\DLAB_CRM\data\dlab.db`

---

## Solucion de problemas

### "No se encuentra el modulo app"
Asegurate de estar dentro de la carpeta `dlab-app` y haber activado el entorno virtual.

### Error de SQLite al compilar
Verifica que `dlab-data/data/dlab.db` exista en la carpeta hermana del proyecto.

### PowerShell bloquea activacion del venv
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### La app no abre el navegador
Abre manualmente `http://127.0.0.1:5000`

---

## Comandos rapidos

| Accion | Comando |
|--------|---------|
| Activar venv | `.venv\Scripts\Activate.ps1` |
| Instalar deps | `pip install -r requirements.txt` |
| Ejecutar app | `python run_local.py` |
| Ejecutar tests | `pytest tests/ -v` |
| Compilar exe | `pyinstaller build_app.spec --clean -y` |
| Build completo | `python build_release.py` |
