from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import settings
from app.db import Base
from app import models  # noqa: F401  (ensures models are registered on Base.metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)



def _target_url() -> str:
    """Which books file to migrate. books.upgrade passes one explicitly; on the command line use
    `alembic -x db=<path> ...`, or fall back to BUDGETER_DATABASE_URL (handy for autogenerating
    against a scratch file)."""
    url = config.attributes.get("db_url")
    if url:
        return url
    path = context.get_x_argument(as_dictionary=True).get("db")
    if path:
        return f"sqlite:///{path}"
    return settings.database_url


config.set_main_option("sqlalchemy.url", _target_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
