"""Операторские команды: приглашение и восстановление без ручного SQL."""
import argparse
from datetime import timedelta
import getpass
import secrets
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import Credentials, digest, now, passwords, setup_lock
from .core import get_settings, make_engine
from .models import Admin, AdminSession, SetupInvite


def create_invite(session, hours=24):
    setup_lock(session)
    if session.scalar(select(Admin.id).limit(1)):
        raise ValueError("Администратор уже создан. Используйте панель или команду recover.")
    session.execute(delete(SetupInvite))
    code = secrets.token_urlsafe(32)
    session.add(SetupInvite(id=1, token_hash=digest(code), expires_at=now() + timedelta(hours=hours)))
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["invite", "recover", "demo"])
    args = parser.parse_args()
    try:
        if args.command == "recover":
            username = input("Логин администратора: ").strip().lower()
            password = getpass.getpass("Новый пароль (от 16 символов): ")
            if password != getpass.getpass("Повторите пароль: "):
                raise ValueError("Пароли не совпадают")
            data = Credentials(username=username, password=password)
        engine = make_engine(get_settings())
        with Session(engine) as session, session.begin():
            if args.command == "invite":
                code = create_invite(session)
            elif args.command == "demo":
                from .demo import create_demo
                create_demo(session)
            else:
                setup_lock(session)
                admin = session.scalar(select(Admin).where(Admin.username == data.username))
                if not admin:
                    raise ValueError("Такого администратора нет; для первого аккаунта используйте invite")
                admin.is_active = True
                admin.password_hash = passwords.hash(data.password.get_secret_value())
                session.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
        engine.dispose()
        if args.command == "invite":
            print("Откройте /admin и выберите «Есть приглашение». Код действует 24 часа:")
            print(code)
            print("Передайте код клиенту по защищённому каналу. Старое приглашение аннулировано.")
        else:
            print("Операция выполнена.")
    except Exception as error:
        # Не печатаем ValidationError, SQL и поля пароля.
        print(str(error) if isinstance(error, ValueError) and not hasattr(error, "errors") else "Операция не выполнена. Проверьте настройки и доступ к базе.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
