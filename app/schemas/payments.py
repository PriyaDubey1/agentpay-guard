from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)
    merchant: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    purpose: str = Field(min_length=1, max_length=500)
    user_goal: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=5000,
                                description="Untrusted text the agent read (e.g. a product page)")


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=300)


class AuditOut(BaseModel):
    event_type: str
    from_state: str | None
    to_state: str | None
    actor: str
    details: dict | None
    created_at: datetime


class PaymentOut(BaseModel):
    id: str
    agent_id: str
    merchant: str
    amount: str
    currency: str
    purpose: str
    user_goal: str | None
    state: str
    risk_score: int
    reasons: list[str]
    paypal_order_id: str | None
    approval_url: str | None
    paypal_capture_id: str | None
    error: str | None
    created_at: datetime
    events: list[AuditOut] | None = None
