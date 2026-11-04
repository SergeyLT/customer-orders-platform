"""Запустить тесты backend с отдельной PostgreSQL и удалить только тестовые ресурсы."""

import argparse
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, **kwargs):
    return subprocess.run(["docker", *args], cwd=ROOT, check=True, **kwargs)


def check(image: str) -> None:
    name = "orders-backend-test-" + secrets.token_hex(4)
    password = secrets.token_urlsafe(24)
    network = name + "-network"
    run("network", "create", "--internal", network, capture_output=True)
    try:
        run("run", "-d", "--name", name, "--network", network, "--network-alias", "postgres",
            "-e", "POSTGRES_DB=customer_orders_test", "-e", "POSTGRES_USER=orders_admin",
            "-e", "POSTGRES_PASSWORD=" + password, "postgres:17-alpine", capture_output=True)
        for attempt in range(60):
            result = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "orders_admin", "-d", "customer_orders_test"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Тестовая PostgreSQL не запустилась")
        # Протокол подготовки ограниченной роли совпадает с рабочим сервером.
        from create_app_database_user import provision
        provision(name, "customer_orders_test", "orders_admin", password)
        run("run", "--rm", "--network", network,
            "-e", "DB_HOST=postgres", "-e", "POSTGRES_DB=customer_orders_test",
            "-e", "APP_DB_PASSWORD=" + password, "-e", "JWT_SECRET=" + secrets.token_urlsafe(32),
            "-e", "COOKIE_SECURE=false", "-e", "PUBLIC_ORIGIN=http://testserver",
            image)
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="customer-orders-backend:test")
    check(parser.parse_args().image)
