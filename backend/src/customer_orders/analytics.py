"""Ограниченный сбор событий по согласию, суточные агрегаты и retention."""
from datetime import timedelta
import secrets
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from .auth import AdminDep, digest, now
from .core import SessionDep
from .models import AnalyticsBatch, AnalyticsDaily, AuthLimit, AdminSession, BehaviorEvent, Visit, VisitDay

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisitWrite(Input):
    consent: Literal[True]
    device: Literal["desktop", "mobile"]
    layout: Literal["orders-v1"] = "orders-v1"


class EventWrite(Input):
    kind: Literal["cursor", "click", "selected", "attempted", "submitted"]
    target: Literal["page", "service", "form", "submit", "cta", "navigation", "details"] = "page"
    x: int | None = Field(default=None, ge=0, le=10000, strict=True)
    y: int | None = Field(default=None, ge=0, le=10000, strict=True)
    width: int = Field(ge=200, le=16000, strict=True)
    height: int = Field(ge=200, le=100000, strict=True)

    @model_validator(mode="after")
    def coordinates(self):
        if self.kind in ("cursor", "click") and (self.x is None or self.y is None):
            raise ValueError("Нужны обе координаты")
        return self


class BatchWrite(Input):
    visit_id: UUID
    token: str = Field(min_length=32, max_length=100)
    batch_id: UUID
    active_ms: int = Field(ge=0, le=86400000, strict=True)
    events: list[EventWrite] = Field(max_length=30)


router = APIRouter(prefix="/api/analytics", tags=["Поведенческая аналитика"])


def add_daily(session, day, device, **counts):
    values = dict(visits=0, active_ms=0, selected=0, attempted=0, submitted=0)
    values.update(counts)
    stmt = insert(AnalyticsDaily).values(day=day, device=device, **values)
    session.execute(stmt.on_conflict_do_update(index_elements=[AnalyticsDaily.day, AnalyticsDaily.device], set_={key: getattr(AnalyticsDaily, key) + value for key, value in counts.items()}))


@router.post("/visits", status_code=201)
def visit(data: VisitWrite, session: SessionDep):
    token = secrets.token_urlsafe(32)
    vid = uuid4()
    day = now().date()
    with session.begin():
        session.add(Visit(id=vid, token_hash=digest(token), device=data.device, layout=data.layout))
        session.flush()
        session.add(VisitDay(visit_id=vid, day=day))
        add_daily(session, day, data.device, visits=1)
    return {"visit_id": vid, "token": token}


@router.post("/batches", status_code=202)
def batch(data: BatchWrite, session: SessionDep):
    with session.begin():
        record = session.scalar(select(Visit).where(Visit.id == data.visit_id).with_for_update())
        if not record or record.created_at < now() - timedelta(hours=24) or not secrets.compare_digest(record.token_hash, digest(data.token)):
            raise HTTPException(403, "Посещение недействительно")
        existing = session.get(AnalyticsBatch, data.batch_id)
        if existing:
            if existing.visit_id != record.id:
                raise HTTPException(409, "Код пакета уже использован")
            return {"accepted": True, "duplicate": True}
        if (now() - record.last_at).total_seconds() < 1 and record.active_ms:
            raise HTTPException(429, "Слишком частая отправка")
        # Серверное ограничение: активное время не может расти быстрее реального.
        delta = min(max(0, data.active_ms - record.active_ms), max(0, int((now() - record.last_at).total_seconds() * 1000)), 30000)
        record.active_ms += delta
        record.last_at = now()
        session.add(AnalyticsBatch(id=data.batch_id, visit_id=record.id))
        day = now().date()
        visit_day = session.get(VisitDay, (record.id, day))
        counts = {"active_ms": delta}
        if not visit_day:
            visit_day = VisitDay(visit_id=record.id, day=day, selected=False, attempted=False, submitted=False)
            session.add(visit_day)
            counts["visits"] = 1
        # Посещение ограничено 24 часами. Не более 1 cursor/сек в среднем.
        if session.scalar(select(func.count()).select_from(BehaviorEvent).where(BehaviorEvent.visit_id == record.id)) > 100000:
            raise HTTPException(429, "Достигнут лимит событий посещения")
        cursor_count = 0
        for item in data.events:
            if item.kind == "cursor":
                cursor_count += 1
                if cursor_count > 10:
                    continue
            if item.kind in ("selected", "attempted", "submitted") and not getattr(visit_day, item.kind):
                setattr(visit_day, item.kind, True)
                counts[item.kind] = 1
            session.add(BehaviorEvent(visit_id=record.id, **item.model_dump()))
        add_daily(session, day, record.device, **counts)
    return {"accepted": True, "duplicate": False}


def cleanup(session):
    # Один worker выполняет чистку; агрегаты уже обновлены при приёме.
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(721035821)")):
        return
    session.execute(delete(Visit).where(Visit.created_at < now() - timedelta(days=30)))
    session.execute(delete(AnalyticsDaily).where(AnalyticsDaily.day < (now() - timedelta(days=365)).date()))
    session.execute(delete(AdminSession).where(AdminSession.expires_at < now()))
    session.execute(delete(AuthLimit).where(AuthLimit.expires_at < now()))


reports = APIRouter(prefix="/api/admin", tags=["Аналитика"])


@reports.get("/analytics")
def report(session: SessionDep, admin: AdminDep, days: Literal[1, 7, 30] = 7, device: Literal["desktop", "mobile"] = "desktop", kind: Literal["cursor", "click"] = "cursor"):
    periods = []
    today = now().date()
    for count in (1, 7, 30):
        rows = list(session.scalars(select(AnalyticsDaily).where(AnalyticsDaily.day >= today - timedelta(days=count - 1), AnalyticsDaily.device == device)))
        visits = sum(row.visits for row in rows)
        periods.append({"days": count, "visits": visits, "average_active_seconds": round(sum(row.active_ms for row in rows) / max(visits, 1) / 1000, 1), **{name: sum(getattr(row, name) for row in rows) for name in ("selected", "attempted", "submitted")}})
    since = now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    # Группируем в сетку 40×60, не отдаём огромный массив сырых движений.
    x = func.floor(BehaviorEvent.x / 250)
    y = func.floor(BehaviorEvent.y / (10000 / 60))
    points = session.execute(select(x.label("x"), y.label("y"), func.count().label("count")).join(Visit, Visit.id == BehaviorEvent.visit_id).where(Visit.device == device, Visit.layout == "orders-v1", BehaviorEvent.kind == kind, BehaviorEvent.created_at >= since).group_by(x, y))
    clicks = session.execute(select(BehaviorEvent.target, func.count()).join(Visit, Visit.id == BehaviorEvent.visit_id).where(Visit.device == device, BehaviorEvent.kind == "click", BehaviorEvent.created_at >= since).group_by(BehaviorEvent.target))
    return {"timezone": "UTC", "device": device, "layout": "orders-v1", "periods": periods, "heatmap": [{"x": int(px), "y": int(py), "count": count} for px, py, count in points], "clicks": [{"target": target, "count": count} for target, count in clicks]}
