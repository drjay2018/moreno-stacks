================================================================================
  DLAB-DATA CRM — GUÍA DE CONEXIÓN POWER BI
  Inteligencia de Negocio — Inmobiliaria
================================================================================

REQUISITO PREVIO
----------------
Tener instalado Power BI Desktop (gratuito):
  https://powerbi.microsoft.com/es-es/downloads/

================================================================================
PASO 1 — ABRIR POWER BI DESKTOP
================================================================================
1. Abre Power BI Desktop desde el menú Inicio.
2. En la pantalla de inicio, haz clic en "Obtener datos" o en la cinta de 
   opciones: Inicio → Obtener datos.

================================================================================
PASO 2 — CONECTAR A LA BASE DE DATOS SQLite
================================================================================
1. En el cuadro "Obtener datos", busca "ODBC" y selecciónalo.
2. En "Cadena de conexión DSN", selecciona "Ninguno" y en la opción 
   "Cadena de conexión" escribe exactamente lo siguiente:

   Driver={SQLite3 ODBC Driver};Database=C:\Users\TU_USUARIO\AppData\Roaming\DLAB_CRM\data\dlab.db

   NOTA IMPORTANTE: Sustituye "TU_USUARIO" por tu nombre de usuario real en Windows. 
   La base de datos operativa se guarda en tu carpeta Roaming para no perder 
   datos al actualizar el sistema.

3. Haz clic en Aceptar.

================================================================================
  ALTERNATIVA (si SQLite ODBC no está instalado)
================================================================================
  En esta misma carpeta ('powerbi') se ha incluido el instalador:
  👉 sqliteodbc_w64.exe

  1. Haz doble clic en el archivo para instalarlo.
  2. Dale "Siguiente" a todo.
  3. Reinicia Power BI Desktop y vuelve a intentar.
  
  (Si prefieres descargarlo tú mismo: http://www.ch-werner.de/sqliteodbc/)

================================================================================
PASO 3 — SELECCIONAR LAS TABLAS
================================================================================
Cuando se conecte, verás el Navegador con las siguientes tablas disponibles:

  TABLA              CONTENIDO
  ─────────────────  ────────────────────────────────────────────────
  entidades          Proyectos inmobiliarios (constructoras)
  clientes           Registro de clientes y leads
  contrapartes       Proveedores / contrapartes de negocio
  compromisos        Compromisos de compra-venta (pre-cierres)
  transacciones      Cierres de ventas completados
  cobros             Cobros por cuotas y financiamiento
  pagos              Pagos a proveedores y comisiones
  gastos             Gastos operativos del negocio
  incidentes         Registro de incidentes y reclamos
  usuarios           Usuarios del sistema (equipo)
  auditoria          Log de cambios realizados en el sistema

Selecciona las tablas que necesitas y haz clic en "Cargar" o "Transformar datos".

================================================================================
PASO 4 — RELACIONES SUGERIDAS
================================================================================
En el modelo de datos (vista de modelo), conecta las tablas así:

  compromisos.cliente_id       → clientes.id
  compromisos.proyecto_id      → entidades.id
  transacciones.compromiso_id  → compromisos.id
  cobros.cierre_id             → transacciones.id
  pagos.transaccion_id         → transacciones.id
  incidentes.cliente_id        → clientes.id

================================================================================
PASO 5 — GUARDAR EL ARCHIVO .PBIX
================================================================================
Guarda tu reporte como:
  powerbi\DLAB_BI.pbix

De esta manera, cuando el usuario haga clic en el botón "Power BI" dentro 
del CRM, el sistema abrirá directamente este archivo.

================================================================================
ACTUALIZAR DATOS EN POWER BI
================================================================================
Cada vez que quieras ver los datos más recientes del CRM:

  OPCIÓN A (Recomendada): 
    En Power BI → Inicio → "Actualizar"
    Power BI leerá directamente el dlab.db actualizado.

  OPCIÓN B:
    Desde el CRM → Sección "Reportería" → Exportar BI
    Esto genera los archivos JSON/Parquet con los datos del período deseado.

================================================================================
SOPORTE
================================================================================
  Carpeta del sistema:  %LOCALAPPDATA%\DLAB_CRM\
  Base de datos viva:   %APPDATA%\DLAB_CRM\data\dlab.db
  Exports BI:           .\dlab-data\exports\BI\
  Este archivo:         .\powerbi\README_PowerBI.txt

================================================================================
