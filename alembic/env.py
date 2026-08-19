import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Run as its own process (alembic CLI), not imported by app.main — needs the
# project root on sys.path the same way scripts/test_pipeline.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the app's own engine (app/core/db.py) instead of building a second
# one from alembic.ini's sqlalchemy.url — sidesteps ConfigParser's own `%`
# interpolation choking on DATABASE_URL's percent-encoded characters (e.g.
# `%40` for `@` in a password), and keeps exactly one place (.env via
# app.core.config.settings) that knows the real connection string.
from app.core.db import Base, engine  # noqa: E402

# Import every model module so its table is registered on Base.metadata
# before autogenerate diffs against it — same imports app/main.py and
# app/worker.py both need for the same reason (SQLAlchemy needs every
# mapped class imported before mapper configuration runs).
from app.models import asset as asset_models  # noqa: E402,F401
from app.models import generation_job as generation_job_models  # noqa: E402,F401
from app.models import invite as invite_models  # noqa: E402,F401
from app.models import product_import as product_import_models  # noqa: E402,F401
from app.models import team as team_models  # noqa: E402,F401
from app.models import tool as tool_models  # noqa: E402,F401
from app.models import user as user_models  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Uses the app's own engine directly (see the import above) rather than
    building a second one from alembic.ini.
    """
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
