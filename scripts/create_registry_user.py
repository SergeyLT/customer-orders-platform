"""Создать bcrypt-запись Registry, не передавая пароль через аргументы процесса."""

import argparse
import getpass
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--file", type=Path, default=Path(".secrets/registry.htpasswd"))
    parser.add_argument("--replace", action="store_true", help="Заменить пароль существующего пользователя")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", args.username):
        parser.error("Имя должно начинаться с латинской буквы или цифры и содержать не более 64 букв, цифр, точек, дефисов или подчёркиваний")
    lines = args.file.read_text(encoding="utf-8").splitlines() if args.file.exists() else []
    prefix = args.username + ":"
    if any(line.startswith(prefix) for line in lines) and not args.replace:
        parser.error("Пользователь уже существует; для смены пароля укажите --replace")
    password = getpass.getpass("Пароль нового пользователя Registry: ")
    if len(password) < 16 or len(password.encode("utf-8")) > 72 or any(ord(character) < 32 for character in password):
        parser.error("Нужен пароль от 16 символов, не более 72 байт UTF-8, без управляющих символов")
    if password != getpass.getpass("Повторите пароль: "):
        parser.error("Пароли не совпадают")
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "htpasswd", "httpd:2.4-alpine", "-niB", args.username],
        input=password + "\n", text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise SystemExit("Не удалось создать bcrypt-запись. Проверьте Docker и доступность httpd:2.4-alpine.")
    entry = result.stdout.strip()
    if not entry.startswith(prefix + "$2") or "\n" in entry:
        raise SystemExit("Некорректный результат htpasswd; файл не изменён.")
    lines = [line for line in lines if not line.startswith(prefix)] + [entry]
    args.file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=args.file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write("\n".join(lines) + "\n")
        os.replace(temporary, args.file)
        args.file.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"Учётная запись сохранена в {args.file}. Файл содержит хеши паролей, не добавляйте его в Git.")


if __name__ == "__main__":
    main()
