"""Воспроизводимые синтетические заявки; запуск только явно оператором."""
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select
from .models import Application, BehaviorMetrics, Service
from .priority import assign

EXAMPLES = [
    ("Анна Примерова", "Сегодня", "Нужна интеграция CRM для распределения обращений.", "Сотрудник", None, "high"),
    ("Борис Тестов", "Завтра", "Требуется бот для клиентов и запись обращений.", "Руководитель", None, "high"),
    ("Вера Макетова", "В течение недели", "Нужен обмен данными между системами.", "Сотрудник", "min", "high"),
    ("Глеб Демов", "Срочно", "Нужна автоматизация процесса уведомлений.", None, "max", "high"),
    ("Дарья Примерова", "В течение месяца", "Нужна интеграция CRM.", None, None, "medium"),
    ("Егор Тестов", None, "Вручную переносим заявки, нужно передавать их в CRM.", None, None, "medium"),
    ("Жанна Макетова", None, "Нужно настроить бот для клиентов.", None, None, "medium"),
    ("Захар Демов", None, "Пока изучаем возможности и хотим узнать подробности.", None, None, "low"),
    ("Ирина Примерова", "В следующем квартале", "Интересует интеграция рабочих систем.", None, None, "low"),
    ("Кирилл Тестов", None, "Нужна предварительная консультация по нашему проекту.", "Сотрудник", None, "low"),
]


def create_demo(session):
    service = session.scalar(select(Service).where(Service.is_active).order_by(Service.id).limit(1))
    if not service:
        raise ValueError("Сначала создайте хотя бы одну активную услугу")
    for index, (name, deadline, task, role, budget, expected) in enumerate(EXAMPLES):
        key = uuid5(NAMESPACE_URL, f"customer-orders-demo-v1-{index}")
        if session.scalar(select(Application.id).where(Application.idempotency_key == key)):
            continue
        record = Application(idempotency_key=key, payload_hash=sha256(str(key).encode()).hexdigest(), service_id=service.id, service_title=service.title, name=name, email=f"demo{index+1}@example.com", task_description=task, desired_deadline=deadline, role=role, budget=service.budget_min if budget == "min" else service.budget_max if budget == "max" else None, company="Синтетический пример", preferred_contact="email", status="new", comment="Демонстрационные данные v1. Можно удалить.")
        assign(record, service)
        if record.priority_evaluation["level"] != expected:
            raise ValueError("Оценка примеров изменилась — обновите сценарии")
        record.metrics = BehaviorMetrics(elapsed_ms=30000 + index * 1000, submission_attempts=1, returning_visitor=False)
        session.add(record)
