import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
from app.config import settings
from app import models  # noqa: F401  # 确保所有 SQLAlchemy 模型注册到 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def include_object(obj, name, type_, reflected, compare_to):
    """跳过 PostGIS 自带的 tiger / topology schema 中的对象。

    这些是 PostGIS 扩展自带的 geocoder 表（edges / addr / county 等），
    由 CREATE EXTENSION postgis_tiger_geocoder 创建，alembic 不应管理它们。
    """
    if hasattr(obj, "schema") and obj.schema in {"tiger", "tiger_data", "topology"}:
        return False
    return True


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
