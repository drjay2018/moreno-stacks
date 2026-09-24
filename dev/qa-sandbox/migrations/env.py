"""
env.py — Alembic environment configuration for DLAB CRM.
Uses the Flask app's database configuration.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.config import Config

config = context.config

# Override para pruebas con DB temporal (p.ej. DLAB_ALEMBIC_DB_URI=sqlite:///C:/.../tmp.db)
url_db = os.environ.get("DLAB_ALEMBIC_DB_URI")
if url_db:
    config.set_main_option("sqlalchemy.url", url_db)
else:
    config.set_main_option("sqlalchemy.url", f"sqlite:///{Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
