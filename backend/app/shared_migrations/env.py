from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app import shared_models  # noqa: F401  (ensures models are registered on SharedBase.metadata)
from app.shared_db import SharedBase

config = context.config

if config.config_file_name is not None:
    # Keep the app's own loggers alive: upgrades run inside the server (startup, new books),
    # and the default would silently disable every logger created before this point.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SharedBase.metadata


def _url() -> str:
    """Which shared budget file to migrate. shared_books.upgrade passes one explicitly; on the
    command line use `alembic --name shared -x db=<path> ...`."""
    url = config.attributes.get("db_url")
    if url:
        return url
    path = context.get_x_argument(as_dictionary=True).get("db")
    if path:
        return f"sqlite:///{path}"
    raise RuntimeError("pass -x db=<path>")


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
