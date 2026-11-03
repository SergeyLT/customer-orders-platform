"""Настройки, подключение к PostgreSQL и административная авторизация."""

from collections.abc import Iterator
from functools import lru_cache
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    db_host: str = "postgres"
    db_port: int = 5432
    postgres_db: str = "customer_orders"
    app_db_user: str = "orders_app"
    app_db_password: SecretStr
    admin_username: str = "admin"
    admin_password: SecretStr = Field(min_length=24)
    app_version: str = "dev"
    release_id: str = "local"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg", username=self.app_db_user,
            password=self.app_db_password.get_secret_value(), host=self.db_host,
            port=self.db_port, database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5,
        hide_parameters=True, connect_args={"connect_timeout": 5, "options": "-csearch_path=orders,pg_catalog -cstatement_timeout=10000"},
    )


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.sessions
    with factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
security = HTTPBasic(realm="Customer Orders Administration")


def require_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    settings = get_settings()
    username_ok = secrets.compare_digest(credentials.username.encode(), settings.admin_username.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), settings.admin_password.get_secret_value().encode())
    if not (username_ok and password_ok):
        raise HTTPException(401, "Требуется авторизация администратора", headers={"WWW-Authenticate": 'Basic realm="Customer Orders Administration"'})
    return credentials.username
