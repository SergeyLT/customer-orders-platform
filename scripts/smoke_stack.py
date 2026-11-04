"""Проверить web → Nginx → backend → PostgreSQL на изолированном локальном стеке."""

import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DEMO_SERVICES = [
    {"slug": "lead-processing", "title": "Обработка заявок", "description": "Сбор обращений с сайта, распределение и уведомления ответственных.", "budget_min": 30000, "budget_max": 120000},
    {"slug": "system-integration", "title": "Интеграция систем", "description": "Обмен данными между CRM, сайтом и другими рабочими сервисами.", "budget_min": 50000, "budget_max": 200000},
    {"slug": "telegram-bot", "title": "Клиентский Telegram-бот", "description": "Диалог с клиентами, сбор заявок и уведомления в Telegram.", "budget_min": 40000, "budget_max": 150000},
]


def check(version: str, release: str, *, keep: bool = False) -> None:
    project = "orders-stack-check-" + secrets.token_hex(4)
    directory = ROOT / ".tmp" / project
    directory.mkdir(parents=True)
    override = directory / "override.json"
    override.write_text(json.dumps({"services": {
        "web": {"image": "customer-orders-web:check"},
        "backend": {"image": "customer-orders-backend:check"},
    }}), encoding="utf-8")
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.local.yaml"), "-f", str(override)]
    environment = dict(os.environ, LOCAL_WEB_PORT="0")

    def compose(*args):
        result = subprocess.run(command + list(args), env=environment, text=True, capture_output=True)
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
            raise RuntimeError("Команда локального Compose завершилась с ошибкой")
        return result.stdout.strip()

    try:
        compose("up", "-d", "--wait", "--wait-timeout", "120", "--no-build", "--pull", "never")
        base = "http://" + compose("port", "web", "8080").splitlines()[0]
        admin_http = build_opener(HTTPCookieProcessor(CookieJar()))
        csrf = ""

        def http(path, method="GET", payload=None, *, admin=False, key=None):
            headers = {"Accept": "application/json"}
            if admin:
                headers["X-Requested-With"] = "CustomerOrders"
                if csrf:
                    headers["X-CSRF-Token"] = csrf
            if key:
                headers["Idempotency-Key"] = key
            if payload is not None:
                headers["Content-Type"] = "application/json"
            request = Request(base + path, method=method, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
            try:
                with (admin_http.open(request, timeout=10) if admin else urlopen(request, timeout=10)) as response:
                    return response.status, response.read()
            except HTTPError as error:
                return error.code, error.read()

        for path, component in [("/health", "web"), ("/api/health", "backend")]:
            status, body = http(path)
            assert status == 200
            assert json.loads(body) == {"status": "ok", "component": component, "version": version, "release": release}
        status, page = http("/")
        assert status == 200
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.decode()):
            assert http(asset)[0] == 200, asset
        assert http("/api/admin/docs")[0] == 401
        # Первичная настройка настоящей командой контейнера; код не печатается.
        backend_id = compose("ps", "-q", "backend")
        result = subprocess.check_output(["docker", "exec", backend_id, "python", "-c", "from sqlalchemy.orm import Session; from customer_orders.core import make_engine,get_settings; from customer_orders.manage import create_invite; s=Session(make_engine(get_settings())); code=create_invite(s); s.commit(); print(code)"], text=True).strip()
        status, body = http("/api/auth/setup", "POST", {"code": result, "username": "admin", "password": "local-admin-password-for-development"}, admin=True)
        assert status == 201, body
        csrf = json.loads(body)["csrf_token"]
        status, admin_page = http("/admin")
        assert status == 200
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', admin_page.decode()):
            assert http(asset)[0] == 200, asset
        assert http("/api/admin/docs", admin=True)[0] == 200
        assert http("/assets/swagger-auth.js")[0] == 200
        assert http("/assets/swagger/swagger-ui-bundle.js")[0] == 200
        for service in DEMO_SERVICES:
            assert http("/api/admin/services", "POST", service, admin=True)[0] == 201
        status, body = http("/api/services")
        services = json.loads(body)
        assert status == 200 and len(services) == 3
        payload = {"service_id": services[0]["id"], "name": "Проверка интеграции", "email": "smoke@example.com", "task_description": "Проверка полного прохождения заявки через Nginx и PostgreSQL.", "budget": None, "metrics": {"elapsed_ms": 15000, "submission_attempts": 1, "returning_visitor": False}}
        key = str(uuid4())
        status, body = http("/api/applications", "POST", payload, key=key)
        assert status == 201, body
        receipt = json.loads(body)
        assert http("/api/applications", "POST", payload, key=key)[0] == 200
        status, body = http("/api/admin/applications", admin=True)
        applications = json.loads(body)
        assert status == 200 and len(applications) == 1
        assert applications[0]["id"] == receipt["id"]
        assert applications[0]["metrics"]["elapsed_ms"] == 15000
        assert http("/api/admin/orders", admin=True)[0] == 200
        assert http("/api/admin/dashboard", admin=True)[0] == 200
        for days in (1, 7, 30):
            assert http(f"/api/admin/analytics?days={days}&device=desktop&kind=cursor", admin=True)[0] == 200
        status, body = http("/api/analytics/visits", "POST", {"consent": True, "device": "desktop"})
        assert status == 201, body
        visit = json.loads(body)
        assert http("/api/analytics/batches", "POST", {**visit, "batch_id": str(uuid4()), "active_ms": 0, "events": []})[0] == 202
        # Потеря БД не должна оставлять readiness зелёным.
        compose("stop", "postgres")
        assert http("/api/health")[0] == 503
        compose("start", "postgres")
        for attempt in range(30):
            if http("/api/health")[0] == 200:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Backend не восстановился после возврата БД")
        print("Полный стек: ресурсы frontend, авторизация, 3 услуги, заявка, метрики, повтор и отказ/возврат БД — OK.")
        if keep:
            print("PREVIEW_URL=" + base)
            print("PREVIEW_PROJECT=" + project)
            print("PREVIEW_OVERRIDE=" + str(override))
    finally:
        if not keep:
            compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="dev")
    parser.add_argument("--release", default="local")
    parser.add_argument("--keep", action="store_true", help="Оставить собственный тестовый стек для проверки в браузере")
    args = parser.parse_args()
    check(args.version, args.release, keep=args.keep)
