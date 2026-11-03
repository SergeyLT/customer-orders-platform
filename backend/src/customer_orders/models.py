"""Таблицы предметной области. Полный SQL изменений хранится в миграциях."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Service(Base):
    """CREATE TABLE services (id serial PRIMARY KEY, slug varchar(80) UNIQUE, title varchar(160),
    description text, budget_min integer, budget_max integer, currency varchar(3),
    is_active boolean, created_at timestamptz, updated_at timestamptz);
    """

    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("budget_min >= 0 AND budget_max >= budget_min", name="services_budget_range"),
        CheckConstraint("currency = 'RUB'", name="services_currency"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    budget_min: Mapped[int] = mapped_column(Integer)
    budget_max: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Application(Base):
    """CREATE TABLE applications (id uuid PRIMARY KEY, service_id integer REFERENCES services,
    idempotency_key uuid UNIQUE, payload_hash varchar(64), name varchar(100), email varchar(254),
    phone varchar(32), telegram varchar(32), task_description text, company varchar(160),
    niche varchar(160), company_size varchar(80), role varchar(80), budget integer,
    desired_deadline varchar(120), preferred_contact varchar(20), contact_time varchar(120),
    comment text, status varchar(20), created_at timestamptz);
    """

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="applications_idempotency_key"),
        CheckConstraint("budget IS NULL OR budget >= 0", name="applications_budget"),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL OR telegram IS NOT NULL", name="applications_contact"),
        CheckConstraint("status IN ('new', 'in_progress', 'completed', 'cancelled')", name="applications_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[UUID] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    service_title: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(32))
    telegram: Mapped[str | None] = mapped_column(String(32))
    task_description: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(String(160))
    niche: Mapped[str | None] = mapped_column(String(160))
    company_size: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str | None] = mapped_column(String(80))
    budget: Mapped[int | None] = mapped_column(Integer)
    desired_deadline: Mapped[str | None] = mapped_column(String(120))
    preferred_contact: Mapped[str] = mapped_column(String(20), default="any")
    contact_time: Mapped[str | None] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    metrics: Mapped["BehaviorMetrics"] = relationship(cascade="all, delete-orphan", passive_deletes=True, uselist=False)


class BehaviorMetrics(Base):
    """CREATE TABLE behavior_metrics (application_id uuid PRIMARY KEY REFERENCES applications
    ON DELETE CASCADE, elapsed_ms integer, submission_attempts integer, returning_visitor boolean);
    """

    __tablename__ = "behavior_metrics"
    __table_args__ = (
        CheckConstraint("elapsed_ms BETWEEN 0 AND 86400000", name="metrics_elapsed"),
        CheckConstraint("submission_attempts BETWEEN 1 AND 100", name="metrics_attempts"),
    )
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    submission_attempts: Mapped[int] = mapped_column(Integer)
    returning_visitor: Mapped[bool] = mapped_column(Boolean)
