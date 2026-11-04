"""Отзываемые JWT-сеансы, CSRF и атомарная первичная настройка."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from .core import SessionDep, get_settings
from .models import Admin, AdminSession, AuthLimit, SetupInvite

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
COOKIE = "orders_session"
cookie_scheme = APIKeyCookie(name=COOKIE, auto_error=False)
LOCK = 721035820


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return sha256(value.encode()).hexdigest()


def setup_lock(session):
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK})


def json_guard(request: Request):
    origin = request.headers.get("origin")
    if (request.headers.get("x-requested-with") != "CustomerOrders"
            or request.headers.get("content-type", "").split(";")[0] != "application/json"
            or (origin and origin.rstrip("/") != get_settings().public_origin.rstrip("/"))):
        raise HTTPException(403, "Запрос должен поступать со страницы приложения")


def throttle(session, key, maximum=10):
    # Отдельная транзакция: неудачная авторизация не откатывает счётчик.
    with session.bind.begin() as connection:
        connection.execute(delete(AuthLimit).where(AuthLimit.expires_at < now()))
        stmt = insert(AuthLimit).values(key=key, attempts=1, expires_at=now() + timedelta(minutes=15))
        count = connection.execute(stmt.on_conflict_do_update(index_elements=[AuthLimit.key], set_={"attempts": AuthLimit.attempts + 1}).returning(AuthLimit.attempts)).scalar_one()
    if count > maximum:
        raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут.", headers={"Retry-After": "900"})


def authenticate(request: Request, session):
    invalid = HTTPException(401, "Войдите в административную панель")
    token = request.cookies.get(COOKIE)
    if not token:
        raise invalid
    try:
        claims = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"], audience="orders-admin", issuer="customer-orders", options={"require": ["exp", "iat", "sub", "jti"]})
        sid, aid = UUID(claims["jti"]), UUID(claims["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise invalid from None
    auth_session = session.get(AdminSession, sid)
    admin = session.get(Admin, aid)
    if not auth_session or auth_session.admin_id != aid or auth_session.expires_at <= now() or not admin or not admin.is_active:
        raise invalid
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        origin = request.headers.get("origin")
        if not secrets.compare_digest(csrf, auth_session.csrf) or (origin and origin.rstrip("/") != get_settings().public_origin.rstrip("/")):
            raise HTTPException(403, "Недействительный CSRF-токен")
    request.state.admin_session = auth_session
    # Защищённые обработчики используют собственные транзакции.
    session.commit()
    return admin


def current_admin(request: Request, session: SessionDep, token: Annotated[str | None, Depends(cookie_scheme)]):
    return authenticate(request, session)


AdminDep = Annotated[Admin, Depends(current_admin)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    password: SecretStr = Field(min_length=16, max_length=128)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=128)


class InviteCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=32, max_length=100)


class Setup(Credentials, InviteCode):
    pass


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=16, max_length=128)


class AdminChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    password: SecretStr | None = Field(default=None, min_length=16, max_length=128)


def admin_read(admin):
    return {"id": str(admin.id), "username": admin.username, "is_active": admin.is_active, "created_at": admin.created_at}


def valid_invite(session, code):
    invite = session.get(SetupInvite, 1)
    if session.scalar(select(func.count()).select_from(Admin)) or not invite or invite.expires_at <= now() or not secrets.compare_digest(invite.token_hash, digest(code)):
        raise HTTPException(403, "Приглашение недействительно или срок истёк")
    return invite


def issue_session(session, admin, response):
    sid = uuid4()
    expires = now() + timedelta(hours=8)
    csrf = secrets.token_urlsafe(32)
    session.add(AdminSession(id=sid, admin_id=admin.id, csrf=csrf, expires_at=expires))
    token = jwt.encode({"sub": str(admin.id), "jti": str(sid), "iat": now(), "exp": expires, "aud": "orders-admin", "iss": "customer-orders"}, get_settings().jwt_secret.get_secret_value(), algorithm="HS256")
    response.set_cookie(COOKIE, token, max_age=28800, secure=get_settings().cookie_secure, httponly=True, samesite="strict", path="/api")
    return {"admin": admin_read(admin), "csrf_token": csrf}


router = APIRouter(prefix="/api/auth", tags=["Авторизация"])


@router.post("/setup/check", dependencies=[Depends(json_guard)])
def check_invite(data: InviteCode, session: SessionDep):
    throttle(session, "setup", 30)
    valid_invite(session, data.code.get_secret_value())
    return {"valid": True}


@router.post("/setup", status_code=201, dependencies=[Depends(json_guard)])
def setup(data: Setup, session: SessionDep, response: Response):
    throttle(session, "setup", 30)
    with session.begin():
        setup_lock(session)
        invite = valid_invite(session, data.code.get_secret_value())
        admin = Admin(username=data.username.lower(), password_hash=passwords.hash(data.password.get_secret_value()))
        session.add(admin)
        session.flush()
        session.delete(invite)
        result = issue_session(session, admin, response)
    return result


@router.post("/login", dependencies=[Depends(json_guard)])
def login(data: Login, session: SessionDep, response: Response):
    throttle(session, "login-global", 100)
    throttle(session, "login-" + digest(data.username.lower()), 10)
    with session.begin():
        admin = session.scalar(select(Admin).where(Admin.username == data.username.lower()).with_for_update())
        verified = passwords.verify(data.password.get_secret_value(), admin.password_hash if admin else DUMMY_HASH)
        if not verified or not admin or not admin.is_active:
            raise HTTPException(401, "Неверный логин или пароль")
        session.execute(delete(AuthLimit).where(AuthLimit.key == "login-" + digest(data.username.lower())))
        result = issue_session(session, admin, response)
    return result


@router.get("/me")
def me(request: Request, admin: AdminDep):
    return {"admin": admin_read(admin), "csrf_token": request.state.admin_session.csrf}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: SessionDep, admin: AdminDep):
    session.execute(delete(AdminSession).where(AdminSession.id == request.state.admin_session.id))
    session.commit()
    response.delete_cookie(COOKIE, path="/api", secure=get_settings().cookie_secure, httponly=True, samesite="strict")


@router.post("/password", status_code=204)
def change_password(data: PasswordChange, session: SessionDep, admin: AdminDep):
    with session.begin():
        setup_lock(session)
        record = session.scalar(select(Admin).where(Admin.id == admin.id).with_for_update().execution_options(populate_existing=True))
        if not passwords.verify(data.current_password.get_secret_value(), record.password_hash):
            raise HTTPException(403, "Неверный текущий пароль")
        record.password_hash = passwords.hash(data.new_password.get_secret_value())
        session.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))


admins = APIRouter(prefix="/api/admin/admins", tags=["Администраторы"])


@admins.get("")
def list_admins(session: SessionDep, admin: AdminDep):
    return [admin_read(item) for item in session.scalars(select(Admin).order_by(Admin.created_at))]


@admins.post("", status_code=201)
def add_admin(data: Credentials, session: SessionDep, admin: AdminDep):
    with session.begin():
        setup_lock(session)
        if session.scalar(select(Admin.id).where(Admin.username == data.username.lower())):
            raise HTTPException(409, "Такой логин уже существует")
        record = Admin(username=data.username.lower(), password_hash=passwords.hash(data.password.get_secret_value()))
        session.add(record)
        session.flush()
        return admin_read(record)


@admins.patch("/{admin_id}")
def edit_admin(admin_id: UUID, data: AdminChange, session: SessionDep, admin: AdminDep):
    with session.begin():
        setup_lock(session)
        record = session.scalar(select(Admin).where(Admin.id == admin_id).with_for_update().execution_options(populate_existing=True))
        if not record:
            raise HTTPException(404, "Администратор не найден")
        if data.is_active is False and record.is_active and session.scalar(select(func.count()).select_from(Admin).where(Admin.is_active)) <= 1:
            raise HTTPException(409, "Нельзя отключить последнего активного администратора")
        if data.is_active is not None:
            record.is_active = data.is_active
        if data.password:
            record.password_hash = passwords.hash(data.password.get_secret_value())
        if data.password or data.is_active is False:
            session.execute(delete(AdminSession).where(AdminSession.admin_id == admin_id))
        session.flush()
        return admin_read(record)
