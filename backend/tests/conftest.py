"""Тесты используют отдельную PostgreSQL, переданную контейнерному runner."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from customer_orders.core import get_settings, make_engine
from customer_orders.main import create_app
from customer_orders.start import migrate


@pytest.fixture(scope="session")
def engine():
    settings = get_settings()
    if settings.postgres_db != "customer_orders_test":
        raise RuntimeError("Тесты разрешены только в отдельной базе customer_orders_test")
    migrate()
    database = make_engine(settings)
    yield database
    database.dispose()


@pytest.fixture(autouse=True)
def clean_database(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE applications, services, admins, setup_invites, auth_limits, visits, analytics_daily RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(engine):
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def admin(engine, client):
    from customer_orders.auth import passwords
    from customer_orders.models import Admin
    from sqlalchemy.orm import Session
    with Session(engine) as session, session.begin():
        session.add(Admin(username="admin", password_hash=passwords.hash("test-admin-password-only-123")))
    response = client.post("/api/auth/login", json={"username": "admin", "password": "test-admin-password-only-123"}, headers={"X-Requested-With": "CustomerOrders"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def service(client, admin):
    result = client.post("/api/admin/services", headers=admin, json={
        "slug": "lead-processing", "title": "Обработка заявок",
        "description": "Сбор обращений, распределение и уведомления ответственных.",
        "budget_min": 30000, "budget_max": 120000,
    })
    assert result.status_code == 201, result.text
    return result.json()


@pytest.fixture
def payload(service):
    return {
        "service_id": service["id"], "name": "Анна", "email": "anna@example.com",
        "task_description": "Нужно собирать заявки с сайта и передавать их в CRM.",
        "budget": None, "preferred_contact": "email",
        "metrics": {"elapsed_ms": 12345, "submission_attempts": 1, "returning_visitor": False},
    }
