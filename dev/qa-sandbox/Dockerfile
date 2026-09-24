FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Directorio de datos persistentes (DB + logs) dentro del contenedor
ENV APPDATA=/opt/dlab
RUN mkdir -p /opt/dlab/DLAB_CRM/data

# Expose port
EXPOSE 5000

# Produccion dentro del contenedor: escucha en todas las interfaces
ENV FLASK_ENV=production
# HOST/PORT quedan solo como documentacion: gunicorn no las lee, el bind
# real se fija con --bind en el CMD de abajo (solo run_local.py/run.py
# ejecutados directamente sin gunicorn usan estas variables).
ENV HOST=0.0.0.0
ENV PORT=5000

# Run: servidor WSGI de produccion (gunicorn), no el servidor de
# desarrollo de Werkzeug que usaba "python run_local.py".
#
# --workers 1: create_app() siembra el usuario admin (app/__init__.py)
# con un patron verificar-y-luego-insertar no idempotente durante el
# import del modulo. Con >1 worker, cada proceso de gunicorn importa
# run_local:app en paralelo y varios workers intentan crear el mismo
# admin a la vez, provocando un IntegrityError (UNIQUE constraint) que
# tumba el worker y el master ("Worker failed to boot"). Verificado en
# el homelab: con --workers 2 el contenedor no arranca; con
# --workers 1 arranca limpio. Si en el futuro se necesita mas
# concurrencia, el seed de admin debe hacerse idempotente/con lock
# antes de subir --workers.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "60", "run_local:app"]
