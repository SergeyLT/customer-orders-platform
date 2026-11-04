"""Администраторы, посещения и объяснимая оценка заявок; существующие записи сохраняются."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0002_admin_analytics"
down_revision = "0001_orders"
branch_labels = depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("priority_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("applications", sa.Column("priority_evaluation", JSONB()))
    op.add_column("applications", sa.Column("manual_priority", sa.String(10)))
    op.add_column("applications", sa.Column("priority_comment", sa.String(500)))
    op.create_index("ix_applications_priority_score", "applications", ["priority_score"])
    op.create_table("admins", sa.Column("id", UUID, primary_key=True), sa.Column("username", sa.String(80), nullable=False, unique=True), sa.Column("password_hash", sa.Text, nullable=False), sa.Column("is_active", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("admin_sessions", sa.Column("id", UUID, primary_key=True), sa.Column("admin_id", UUID, sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False), sa.Column("csrf", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_table("setup_invites", sa.Column("id", sa.Integer, primary_key=True), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("auth_limits", sa.Column("key", sa.String(80), primary_key=True), sa.Column("attempts", sa.Integer, nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_limits_expires_at", "auth_limits", ["expires_at"])
    op.create_table("visits", sa.Column("id", UUID, primary_key=True), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("device", sa.String(10), nullable=False), sa.Column("layout", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("last_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("active_ms", sa.Integer, nullable=False))
    op.create_index("ix_visits_created_at", "visits", ["created_at"])
    op.create_table("visit_days", sa.Column("visit_id", UUID, sa.ForeignKey("visits.id", ondelete="CASCADE"), primary_key=True), sa.Column("day", sa.Date, primary_key=True), sa.Column("selected", sa.Boolean, nullable=False), sa.Column("attempted", sa.Boolean, nullable=False), sa.Column("submitted", sa.Boolean, nullable=False))
    op.create_table("analytics_batches", sa.Column("id", UUID, primary_key=True), sa.Column("visit_id", UUID, sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False))
    op.create_index("ix_analytics_batches_visit_id", "analytics_batches", ["visit_id"])
    op.create_table("behavior_events", sa.Column("id", sa.Integer, primary_key=True), sa.Column("visit_id", UUID, sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False), sa.Column("kind", sa.String(20), nullable=False), sa.Column("target", sa.String(30), nullable=False), sa.Column("x", sa.Integer), sa.Column("y", sa.Integer), sa.Column("width", sa.Integer, nullable=False), sa.Column("height", sa.Integer, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_behavior_events_visit_id", "behavior_events", ["visit_id"])
    op.create_index("ix_behavior_events_created_at", "behavior_events", ["created_at"])
    op.create_table("analytics_daily", sa.Column("day", sa.Date, primary_key=True), sa.Column("device", sa.String(10), primary_key=True), *[sa.Column(name, sa.BigInteger if name == "active_ms" else sa.Integer, nullable=False) for name in ("visits", "active_ms", "selected", "attempted", "submitted")])


def downgrade():
    for table in ("analytics_daily", "behavior_events", "analytics_batches", "visit_days", "visits", "auth_limits", "setup_invites", "admin_sessions", "admins"):
        op.drop_table(table)
    for column in ("priority_comment", "manual_priority", "priority_evaluation", "priority_score"):
        op.drop_column("applications", column)
