import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class Agent(Base):
    """An AI agent plus the spending policy that governs it."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("agt"))
    name: Mapped[str] = mapped_column(String)
    api_key_hash: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | suspended
    currency: Mapped[str] = mapped_column(String, default="USD")
    max_per_txn_cents: Mapped[int] = mapped_column(Integer)
    daily_budget_cents: Mapped[int] = mapped_column(Integer)
    auto_approve_below_cents: Mapped[int] = mapped_column(Integer)
    allowed_merchants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_keywords: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("agent_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("pay"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    idempotency_key: Mapped[str] = mapped_column(String)
    merchant: Mapped[str] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(Text)
    user_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String, default="PROPOSED")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    paypal_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_url: Mapped[str | None] = mapped_column(String, nullable=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    """Append-only log. Rows are only ever inserted."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"))
    event_type: Mapped[str] = mapped_column(String)
    from_state: Mapped[str | None] = mapped_column(String, nullable=True)
    to_state: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
