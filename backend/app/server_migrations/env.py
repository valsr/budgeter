from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app import server_models  # noqa: F401  (ensures models are registered on ServerBase.metadata)
from app.server_db import ServerBase, server_db_path

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ServerBase.metadata


def _url() -> str:
    # server_db.upgrade_to_head passes the file explicitly; the CLI
    # (`alembic --name server ...`) falls back to the configured data dir.
    url = config.attributes.get("db_url")
    if url:
        return url
    path = server_db_path()
    if path is None:
        raise RuntimeError("No data directory configured: set BUDGETER_DATA_DIR or BUDGETER_DATABASE_URL")
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
