"""Таблицы предметной области. Полный SQL изменений хранится в миграциях."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from datetime import date
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
    priority_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    priority_evaluation: Mapped[dict | None] = mapped_column(JSONB)
    manual_priority: Mapped[str | None] = mapped_column(String(10))
    priority_comment: Mapped[str | None] = mapped_column(String(500))
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


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    admin_id: Mapped[UUID] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SetupInvite(Base):
    __tablename__ = "setup_invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthLimit(Base):
    __tablename__ = "auth_limits"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64))
    device: Mapped[str] = mapped_column(String(10))
    layout: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    active_ms: Mapped[int] = mapped_column(Integer, default=0)


class VisitDay(Base):
    __tablename__ = "visit_days"
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)


class AnalyticsBatch(Base):
    __tablename__ = "analytics_batches"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), index=True)


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(30))
    x: Mapped[int | None] = mapped_column(Integer)
    y: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    device: Mapped[str] = mapped_column(String(10), primary_key=True)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    active_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    selected: Mapped[int] = mapped_column(Integer, default=0)
    attempted: Mapped[int] = mapped_column(Integer, default=0)
    submitted: Mapped[int] = mapped_column(Integer, default=0)
