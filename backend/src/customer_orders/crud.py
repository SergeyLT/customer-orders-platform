"""Операции с данными. Запись заявки и метрик выполняется одной транзакцией."""

import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .models import Application, BehaviorMetrics, Service
from .schemas import ApplicationWrite, ServiceWrite


def list_services(session: Session, *, include_inactive: bool = False) -> list[Service]:
    query = select(Service).order_by(Service.id)
    if not include_inactive:
        query = query.where(Service.is_active.is_(True))
    return list(session.scalars(query))


def write_service(session: Session, data: ServiceWrite, service_id: int | None = None) -> Service:
    with session.begin():
        service = session.get(Service, service_id) if service_id else Service()
        if service is None:
            raise HTTPException(404, "Услуга не найдена")
        for key, value in data.model_dump().items():
            setattr(service, key, value)
        session.add(service)
        try:
            session.flush()
        except IntegrityError:
            raise HTTPException(409, "Услуга с таким slug уже существует") from None
        # Проверяем сериализацию до commit, чтобы не подтверждать некорректный ответ.
        from .schemas import ServiceRead
        ServiceRead.model_validate(service)
    return service


def create_application(session: Session, data: ApplicationWrite, key: UUID) -> tuple[UUID, bool]:
    values = data.model_dump(mode="json", exclude={"metrics"})
    payload_hash = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with session.begin():
        existing = session.scalar(select(Application).where(Application.idempotency_key == key).with_for_update())
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(409, "Ключ повторной отправки уже использован для другой заявки")
            existing.metrics.submission_attempts = max(existing.metrics.submission_attempts, data.metrics.submission_attempts)
            return existing.id, False
        service = session.scalar(select(Service).where(Service.id == data.service_id, Service.is_active.is_(True)).with_for_update())
        if service is None:
            raise HTTPException(404, "Услуга больше недоступна. Обновите список и выберите другую.")
        if data.budget is not None and not service.budget_min <= data.budget <= service.budget_max:
            raise HTTPException(422, "Бюджет находится за пределами диапазона выбранной услуги")
        application_id = uuid4()
        statement = insert(Application).values(
            **values, id=application_id, idempotency_key=key, payload_hash=payload_hash,
            service_title=service.title, status="new",
        ).on_conflict_do_nothing(index_elements=[Application.idempotency_key]).returning(Application.id)
        created_id = session.scalar(statement)
        if created_id is None:
            existing = session.scalar(select(Application).where(Application.idempotency_key == key))
            if existing is None or existing.payload_hash != payload_hash:
                raise HTTPException(409, "Конфликт повторной отправки заявки")
            existing.metrics.submission_attempts = max(existing.metrics.submission_attempts, data.metrics.submission_attempts)
            return existing.id, False
        session.add(BehaviorMetrics(application_id=created_id, **data.metrics.model_dump()))
    return created_id, True


def get_application(session: Session, application_id: UUID) -> Application:
    record = session.scalar(select(Application).where(Application.id == application_id).options(selectinload(Application.metrics)))
    if record is None:
        raise HTTPException(404, "Заявка не найдена")
    return record
