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
    if services["web"].get("ports") or services["postgres"].get("ports"):
        raise ValueError("Web и PostgreSQL не должны публиковать host-порты")
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
