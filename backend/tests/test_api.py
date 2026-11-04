from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from customer_orders.models import BehaviorMetrics


def test_catalog_lists_all_three_services(client, admin, service):
    for slug, title in [("integration", "Интеграция систем"), ("telegram", "Клиентский Telegram-бот")]:
        result = client.post("/api/admin/services", headers=admin, json={
            "slug": slug, "title": title, "description": "Настройка взаимодействия рабочих систем.",
            "budget_min": 40000, "budget_max": 200000,
        })
        assert result.status_code == 201
    assert len(client.get("/api/services").json()) == 3
    changed = client.put(f"/api/admin/services/{service['id']}", headers=admin, json={
        **{key: value for key, value in service.items() if key != "id"}, "title": "Заявки из разных каналов",
    })
    assert changed.status_code == 200
    assert changed.json()["title"] == "Заявки из разных каналов"


@pytest.mark.parametrize("path", ["/api/admin/services", "/api/admin/applications", "/api/admin/docs", "/api/admin/openapi.json"])
def test_admin_data_and_documentation_require_authentication(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, auth=("admin", "wrong-password")).status_code == 401


def test_protected_openapi_and_self_hosted_swagger(client, admin):
    docs = client.get("/api/admin/docs", headers=admin)
    assert docs.status_code == 200
    assert "/assets/swagger/swagger-ui-bundle.js" in docs.text
    assert "cdn.jsdelivr.net" not in docs.text
    contract = client.get("/api/admin/openapi.json", headers=admin).json()
    assert "/api/applications" in contract["paths"]
    assert contract["paths"]["/api/admin/services"]["post"]["security"]
    assert client.get("/docs").status_code == 404


def test_application_and_metrics_are_saved_without_public_pii(client, admin, payload, engine):
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 201
    receipt = response.json()
    assert set(receipt) == {"id", "message"}
    assert "anna@example.com" not in response.text
    detail = client.get(f"/api/admin/applications/{receipt['id']}", headers=admin).json()
    assert detail["email"] == payload["email"]
    assert detail["service_title"] == "Обработка заявок"
    assert detail["metrics"] == payload["metrics"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applications a JOIN behavior_metrics m ON a.id=m.application_id")).scalar() == 1


def test_idempotent_retry_returns_existing_receipt(client, payload, engine):
    key = str(uuid4())
    first = client.post("/api/applications", json=payload, headers={"Idempotency-Key": key})
    payload["metrics"]["submission_attempts"] = 2
    payload["metrics"]["elapsed_ms"] += 5000
    second = client.post("/api/applications", json=payload, headers={"Idempotency-Key": key})
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applications")).scalar() == 1
        assert connection.execute(text("SELECT submission_attempts FROM behavior_metrics")).scalar() == 2


def test_concurrent_retries_create_one_application(client, payload, engine):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, "/api/applications", json=payload, headers={"Idempotency-Key": key}) for _ in range(2)]
        responses = [future.result() for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applications")).scalar() == 1


def test_reused_key_with_other_data_is_conflict(client, payload):
    key = str(uuid4())
    assert client.post("/api/applications", json=payload, headers={"Idempotency-Key": key}).status_code == 201
    payload["name"] = "Другое имя"
    assert client.post("/api/applications", json=payload, headers={"Idempotency-Key": key}).status_code == 409


@pytest.mark.parametrize("change", [
    {"email": None}, {"preferred_contact": "telegram"}, {"phone": "not-a-phone"},
    {"telegram": "bad"}, {"budget": 1}, {"budget": 120001}, {"budget": "50000"},
    {"task_description": "short"}, {"service_id": 99999},
    {"metrics": {"elapsed_ms": -1, "submission_attempts": 1, "returning_visitor": False}},
])
def test_invalid_application_is_not_saved(client, payload, engine, change):
    response = client.post("/api/applications", json={**payload, **change})
    assert response.status_code in (404, 422)
    assert "anna@example.com" not in response.text
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applications")).scalar() == 0


def test_failure_saving_metrics_rolls_back_application(client, payload, engine, caplog):
    def fail(mapper, connection, target):
        raise RuntimeError("private-person@example.com")
    event.listen(BehaviorMetrics, "before_insert", fail)
    try:
        result = client.post("/api/applications", json=payload)
    finally:
        event.remove(BehaviorMetrics, "before_insert", fail)
    assert result.status_code == 500
    assert "private-person" not in result.text
    assert "private-person" not in caplog.text
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applications")).scalar() == 0


def test_service_deactivation_preserves_old_applications(client, admin, service, payload):
    receipt = client.post("/api/applications", json=payload).json()
    assert client.delete(f"/api/admin/services/{service['id']}", headers=admin).status_code == 204
    assert client.get("/api/services").json() == []
    assert client.post("/api/applications", json=payload).status_code == 404
    assert client.get(f"/api/admin/applications/{receipt['id']}", headers=admin).status_code == 200


def test_status_update_and_deletion_cascade(client, admin, payload, engine):
    receipt = client.post("/api/applications", json=payload).json()
    path = f"/api/admin/applications/{receipt['id']}"
    assert client.patch(path, headers=admin, json={"status": "in_progress"}).json()["status"] == "in_progress"
    assert client.delete(path, headers=admin).status_code == 204
    assert client.get(path, headers=admin).status_code == 404
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM behavior_metrics")).scalar() == 0


def test_no_redirects_and_no_public_application_listing(client, payload):
    result = client.post("/api/applications/", json=payload, follow_redirects=False)
    assert result.status_code == 404
    assert client.get("/api/applications").status_code == 405


def test_application_role_is_not_superuser(client, engine):
    assert client.get("/api/health").json()["component"] == "backend"
    with engine.connect() as connection:
        user, superuser, create_role, create_db = connection.execute(text("SELECT current_user, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname=current_user")).one()
    assert user == "orders_app"
    assert (superuser, create_role, create_db) == (False, False, False)
