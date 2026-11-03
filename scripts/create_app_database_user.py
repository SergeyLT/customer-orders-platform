"""Подготовить ограниченную роль приложения в существующей PostgreSQL через Docker."""

import argparse
import getpass
import re
import subprocess


def provision(container: str, database: str, admin: str, password: str, *, replace: bool = False) -> None:
    for value in (database, admin):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
            raise ValueError("Имя базы и пользователя должно быть SQL-идентификатором в нижнем регистре")
    if len(password) < 24 or any(ord(character) < 32 for character in password):
        raise ValueError("Пароль должен содержать от 24 символов без управляющих символов")
    command = ["docker", "exec", "-i", container, "psql", "-X", "-U", admin, "-d", database, "-v", "ON_ERROR_STOP=1", "-At"]
    check = subprocess.run(command, input="SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orders_app');\n", text=True, capture_output=True, check=True)
    exists = check.stdout.strip() == "t"
    if exists and not replace:
        raise ValueError("Роль orders_app уже существует. Для явной ротации пароля используйте --replace")
    escaped = password.replace("'", "''")
    create = "" if exists else "CREATE ROLE orders_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"
    query = f"""BEGIN;
SET LOCAL standard_conforming_strings = on;
{create}
ALTER ROLE orders_app PASSWORD '{escaped}';
GRANT CONNECT ON DATABASE {database} TO orders_app;
CREATE SCHEMA IF NOT EXISTS orders AUTHORIZATION orders_app;
GRANT USAGE, CREATE ON SCHEMA orders TO orders_app;
COMMIT;
"""
    result = subprocess.run(command, input=query, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Не удалось подготовить роль и схему. Сырой SQL с паролем не выводится; проверьте доступ и существующую схему.")
    print("Роль orders_app и схема orders готовы. Добавьте этот пароль как APP_DB_PASSWORD в Coolify.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True, help="Имя контейнера PostgreSQL проекта")
    parser.add_argument("--database", default="customer_orders")
    parser.add_argument("--admin-user", default="orders_admin")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    password = getpass.getpass("Пароль новой роли orders_app: ")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    try:
        provision(args.container, args.database, args.admin_user, password, replace=args.replace)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            raise SystemExit("Не удалось подключиться к PostgreSQL через Docker exec") from None
        raise SystemExit(str(error)) from None
