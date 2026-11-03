"""Проверить Compose и границы публикации портов без запуска сервисов."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def load_config(filename: str) -> dict:
    result = subprocess.run(
        ["docker", "compose", "--env-file", ".env.example", "-f", filename, "config", "--format", "json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def check() -> None:
    app = load_config("compose.coolify.yaml")
    registry = load_config("compose.registry.yaml")
    services = app["services"]
    if any(services[name].get("ports") for name in ("web", "backend", "postgres")):
        raise ValueError("Web, backend и PostgreSQL не должны публиковать host-порты")
    if set(services["backend"]["networks"]) != {"default", "database"}:
        raise ValueError("Backend должен соединять только сеть приложения и сеть базы")
    if services["backend"]["environment"].get("APP_DB_USER") != "orders_app":
        raise ValueError("Backend должен работать от ограниченной роли orders_app")
    ports = services["pgadmin"].get("ports", [])
    if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1":
        raise ValueError("pgAdmin должен быть опубликован только на localhost")
    if set(services["postgres"]["networks"]) != {"database"}:
        raise ValueError("PostgreSQL должен находиться только в сети database")
    if not app["networks"]["database"].get("internal"):
        raise ValueError("Сеть database должна быть внутренней")
    if registry["services"]["registry"].get("ports"):
        raise ValueError("Registry должен быть доступен через прокси, без host-порта")
    if registry["services"]["registry"]["environment"].get("REGISTRY_AUTH") != "htpasswd":
        raise ValueError("Авторизация Registry обязательна")
    print("Compose: синтаксис и границы доступа проверены.")


if __name__ == "__main__":
    check()
