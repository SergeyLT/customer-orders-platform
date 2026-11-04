"""Список заказов с фильтрами и ручным приоритетом."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from .auth import AdminDep
from .core import SessionDep
from .crud import get_application
from .models import Application
from .schemas import ApplicationRead

router = APIRouter(prefix="/api/admin", tags=["Рабочее место"])


def read_order(item):
    return {**ApplicationRead.model_validate(item).model_dump(mode="json"), "priority": item.priority_evaluation,
            "manual_priority": item.manual_priority, "priority_comment": item.priority_comment,
            "effective_priority": item.manual_priority or (item.priority_evaluation or {}).get("level", "low")}


class PriorityChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: Literal["high", "medium", "low"] | None
    comment: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def reason(self):
        if self.priority and not self.comment.strip():
            raise ValueError("Укажите причину ручного изменения")
        return self


def priority_expression():
    return case((Application.manual_priority == "high", 2), (Application.manual_priority == "medium", 1), (Application.manual_priority == "low", 0), (Application.priority_score >= 65, 2), (Application.priority_score >= 30, 1), else_=0)


@router.get("/orders")
def orders(session: SessionDep, admin: AdminDep, q: Annotated[str, Query(max_length=100)] = "", status: Literal["new", "in_progress", "completed", "cancelled"] | None = None, service_id: int | None = None, priority: Literal["high", "medium", "low"] | None = None, sort: Literal["priority", "newest", "oldest"] = "priority", offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 25):
    filters = []
    if q.strip():
        # Пользовательские %/_ не становятся шаблоном поиска.
        filters.append(or_(*[column.contains(q.strip(), autoescape=True) for column in (Application.name, Application.company, Application.task_description, Application.email)]))
    if status:
        filters.append(Application.status == status)
    if service_id is not None:
        filters.append(Application.service_id == service_id)
    if priority:
        filters.append(priority_expression() == {"high": 2, "medium": 1, "low": 0}[priority])
    total = session.scalar(select(func.count()).select_from(Application).where(*filters))
    ordering = [priority_expression().desc(), case((Application.status == "new", 0), (Application.status == "in_progress", 1), else_=2), Application.created_at.asc(), Application.id] if sort == "priority" else [Application.created_at.desc() if sort == "newest" else Application.created_at.asc(), Application.id]
    items = session.scalars(select(Application).where(*filters).options(selectinload(Application.metrics)).order_by(*ordering).offset(offset).limit(limit))
    return {"items": [read_order(item) for item in items], "total": total, "offset": offset, "limit": limit}


@router.get("/orders/{application_id}")
def order(application_id: UUID, session: SessionDep, admin: AdminDep):
    return read_order(get_application(session, application_id))


@router.patch("/applications/{application_id}/priority")
def change_priority(application_id: UUID, data: PriorityChange, session: SessionDep, admin: AdminDep):
    with session.begin():
        item = get_application(session, application_id)
        item.manual_priority = data.priority
        item.priority_comment = data.comment.strip() if data.priority else None
    return read_order(item)


@router.get("/dashboard")
def dashboard(session: SessionDep, admin: AdminDep):
    def grouped(column):
        return [{"label": label, "count": count} for label, count in session.execute(select(column, func.count()).group_by(column))]
    return {"total": session.scalar(select(func.count()).select_from(Application)), "statuses": grouped(Application.status), "services": grouped(Application.service_title)}
