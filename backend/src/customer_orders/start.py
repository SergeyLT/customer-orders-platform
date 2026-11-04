"""Миграции перед запуском HTTP-сервера; один процесс приложения на контейнер."""

import os
import sys
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .core import get_settings, make_engine


def migrate() -> None:
    engine = make_engine(get_settings())
    try:
        for attempt in range(12):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except SQLAlchemyError:
                if attempt == 11:
                    raise RuntimeError("PostgreSQL недоступен") from None
                time.sleep(2)
        with engine.begin() as connection:
            # Развёртывания одной БД не должны одновременно изменять схему.
            connection.execute(text("SELECT pg_advisory_xact_lock(721035819)"))
            if connection.execute(text("SELECT current_schema()" )).scalar() != "orders":
                raise RuntimeError("Сначала создайте схему orders и ограниченную роль приложения")
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        from sqlalchemy.orm import Session
        from sqlalchemy import select
        from .models import Application, Service
        from .priority import assign
        with Session(engine) as session, session.begin():
            for record in session.scalars(select(Application).where(Application.priority_evaluation.is_(None))):
                assign(record, session.get(Service, record.service_id))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        migrate()
    except Exception:
        print("Не удалось применить миграции. Проверьте доступ к БД и подготовку роли/схемы; данные не удалялись.", file=sys.stderr)
        raise SystemExit(1) from None
    # Coolify может добавлять общие runtime-переменные всем компонентам.
    # HTTP-процесс получает только необходимые ему настройки.
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
               "DB_HOST", "DB_PORT", "POSTGRES_DB", "APP_DB_USER", "APP_DB_PASSWORD",
               "JWT_SECRET", "PUBLIC_ORIGIN", "COOKIE_SECURE", "APP_VERSION", "RELEASE_ID"}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    os.execve(sys.executable, [sys.executable, "-m", "uvicorn", "customer_orders.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--log-config", "logging.json"], environment)
