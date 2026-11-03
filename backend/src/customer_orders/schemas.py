"""Публичный контракт, валидация и безопасные модели ответов."""

from datetime import datetime
import re
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class ServiceWrite(Schema):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=10, max_length=2000)
    budget_min: int = Field(ge=0, le=1_000_000_000, strict=True)
    budget_max: int = Field(ge=0, le=1_000_000_000, strict=True)
    currency: Literal["RUB"] = "RUB"
    is_active: bool = True

    @model_validator(mode="after")
    def budget_range(self) -> Self:
        if self.budget_max < self.budget_min:
            raise ValueError("Максимальный бюджет должен быть не меньше минимального")
        return self


class ServiceRead(ServiceWrite):
    id: int


class MetricsWrite(Schema):
    elapsed_ms: int = Field(ge=0, le=86_400_000, strict=True)
    submission_attempts: int = Field(ge=1, le=100, strict=True)
    returning_visitor: bool = False


class ApplicationWrite(Schema):
    service_id: int = Field(gt=0, strict=True)
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    telegram: str | None = Field(default=None, max_length=33)
    task_description: str = Field(min_length=10, max_length=4000)
    company: str | None = Field(default=None, max_length=160)
    niche: str | None = Field(default=None, max_length=160)
    company_size: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=80)
    budget: int | None = Field(default=None, ge=0, le=1_000_000_000, strict=True)
    desired_deadline: str | None = Field(default=None, max_length=120)
    preferred_contact: Literal["any", "phone", "email", "telegram"] = "any"
    contact_time: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)
    metrics: MetricsWrite

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"\+?[0-9 ()-]+", value) or not 7 <= len(digits) <= 15:
            raise ValueError("Укажите телефон из 7–15 цифр")
        return value

    @field_validator("telegram")
    @classmethod
    def valid_telegram(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"@?[a-zA-Z0-9_]{5,32}", value):
            raise ValueError("Укажите Telegram username из 5–32 символов")
        return value.lstrip("@")

    @model_validator(mode="after")
    def has_contact(self) -> Self:
        if not any((self.email, self.phone, self.telegram)):
            raise ValueError("Укажите хотя бы один контакт: email, телефон или Telegram")
        if self.preferred_contact != "any" and not getattr(self, self.preferred_contact):
            raise ValueError("Заполните контакт для выбранного способа связи")
        return self


class ApplicationReceipt(Schema):
    id: UUID
    message: str = "Заявка отправлена! Мы свяжемся с вами, чтобы уточнить детали."


class ApplicationRead(Schema):
    id: UUID
    service_id: int
    service_title: str
    name: str
    email: str | None
    phone: str | None
    telegram: str | None
    task_description: str
    company: str | None
    niche: str | None
    company_size: str | None
    role: str | None
    budget: int | None
    desired_deadline: str | None
    preferred_contact: str
    contact_time: str | None
    comment: str | None
    status: str
    created_at: datetime
    metrics: MetricsWrite


class ApplicationStatus(Schema):
    status: Literal["new", "in_progress", "completed", "cancelled"]
