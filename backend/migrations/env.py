"""Миграции используют то же подключение и схему, что и приложение."""

from alembic import context

from customer_orders.core import get_settings, make_engine
from customer_orders.models import Base

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = make_engine(get_settings())
    with engine.begin() as connection:
        run(connection)
    engine.dispose()
