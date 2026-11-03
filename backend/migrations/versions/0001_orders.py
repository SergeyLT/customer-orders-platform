"""Первичная схема услуг, заявок и связанных метрик."""

from alembic import op
import sqlalchemy as sa

revision = "0001_orders"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("budget_min", sa.Integer(), nullable=False),
        sa.Column("budget_max", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("budget_min >= 0 AND budget_max >= budget_min", name="services_budget_range"),
        sa.CheckConstraint("currency = 'RUB'", name="services_currency"),
    )
    op.create_table("applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("service_title", sa.String(160), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254)), sa.Column("phone", sa.String(32)), sa.Column("telegram", sa.String(32)),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("company", sa.String(160)), sa.Column("niche", sa.String(160)),
        sa.Column("company_size", sa.String(80)), sa.Column("role", sa.String(80)),
        sa.Column("budget", sa.Integer()), sa.Column("desired_deadline", sa.String(120)),
        sa.Column("preferred_contact", sa.String(20), nullable=False),
        sa.Column("contact_time", sa.String(120)), sa.Column("comment", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="applications_idempotency_key"),
        sa.CheckConstraint("budget IS NULL OR budget >= 0", name="applications_budget"),
        sa.CheckConstraint("email IS NOT NULL OR phone IS NOT NULL OR telegram IS NOT NULL", name="applications_contact"),
        sa.CheckConstraint("status IN ('new', 'in_progress', 'completed', 'cancelled')", name="applications_status"),
    )
    for column in ("service_id", "status", "created_at"):
        op.create_index("ix_applications_" + column, "applications", [column])
    op.create_table("behavior_metrics",
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("submission_attempts", sa.Integer(), nullable=False),
        sa.Column("returning_visitor", sa.Boolean(), nullable=False),
        sa.CheckConstraint("elapsed_ms BETWEEN 0 AND 86400000", name="metrics_elapsed"),
        sa.CheckConstraint("submission_attempts BETWEEN 1 AND 100", name="metrics_attempts"),
    )


def downgrade():
    op.drop_table("behavior_metrics")
    op.drop_table("applications")
    op.drop_table("services")
