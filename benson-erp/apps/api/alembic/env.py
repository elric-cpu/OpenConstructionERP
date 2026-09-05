import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import settings
from app.core.database import Base
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.documents import models as document_models  # noqa: F401
from app.modules.estimating import models as estimating_models  # noqa: F401
from app.modules.federal_labor import models as federal_labor_models  # noqa: F401
from app.modules.payroll import models as payroll_models  # noqa: F401
from app.modules.people import models as people_models  # noqa: F401
from app.modules.platform import models as platform_models  # noqa: F401
from app.modules.projects import models as project_models  # noqa: F401
from app.modules.scheduling import models as scheduling_models  # noqa: F401
from app.modules.timekeeping import models as timekeeping_models  # noqa: F401
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.migration_database_url or settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
