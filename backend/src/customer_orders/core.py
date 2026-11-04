"""Настройки, подключение к PostgreSQL и административная авторизация."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from pydantic import Field, SecretStr, model_validator
from urllib.parse import urlsplit
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
    jwt_secret: SecretStr = Field(min_length=32)
    public_origin: str = "https://orders.example.com"
    cookie_secure: bool = True
    app_version: str = "dev"
    release_id: str = "local"

    @model_validator(mode="after")
    def origin_is_valid(self):
        origin = urlsplit(self.public_origin)
        if not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ("", "/") or origin.scheme not in ("http", "https"):
            raise ValueError("PUBLIC_ORIGIN должен содержать только схему, хост и при необходимости порт")
        if self.cookie_secure and origin.scheme != "https":
            raise ValueError("Для production требуется HTTPS origin")
        return self

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
