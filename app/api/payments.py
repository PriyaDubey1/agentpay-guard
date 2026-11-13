import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_agent, get_paypal, require_admin
from app.db import get_db
from app.models.tables import Agent, AuditEvent, Payment, utcnow
from app.schemas.payments import DecisionRequest, PaymentOut, PaymentRequest
from app.services import executor
from app.services.policy import decide, spent_today_cents
from app.services.state import audit, transition

router = APIRouter(prefix="/v1")

# Serialises decide+insert so two simultaneous proposals can't both squeeze
# under the same daily budget. (Single-process demo; use row locks on Postgres.)
_DECIDE_LOCK = threading.Lock()


def to_out(db: Session, p: Payment, events: bool = False) -> PaymentOut:
    out = PaymentOut(
        id=p.id, agent_id=p.agent_id, merchant=p.merchant,
        amount=f"{p.amount_cents / 100:.2f}", currency=p.currency, purpose=p.purpose,
        user_goal=p.user_goal, state=p.state, risk_score=p.risk_score,
        reasons=p.reasons or [], paypal_order_id=p.paypal_order_id,
        approval_url=p.approval_url, paypal_capture_id=p.paypal_capture_id,
        error=p.error, created_at=p.created_at,
    )
    if events:
        rows = db.execute(select(AuditEvent).where(AuditEvent.payment_id == p.id)
                          .order_by(AuditEvent.id)).scalars().all()
        out.events = [dict(event_type=e.event_type, from_state=e.from_state, to_state=e.to_state,
                           actor=e.actor, details=e.details, created_at=e.created_at) for e in rows]
    return out


def _get(db: Session, payment_id: str) -> Payment:
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(404, "Payment not found")
    return p


@router.post("/payments", response_model=PaymentOut, status_code=201)
def propose_payment(req: PaymentRequest, agent: Agent = Depends(current_agent),
                    db: Session = Depends(get_db), paypal=Depends(get_paypal)):
    """Called by the AI agent. The agent can only PROPOSE; the Guard decides."""
    amount_cents = int((req.amount * 100).to_integral_value())

    existing = db.execute(select(Payment).where(
        Payment.agent_id == agent.id, Payment.idempotency_key == req.idempotency_key
    )).scalar_one_or_none()
    if existing:
        if (existing.merchant, existing.amount_cents, existing.currency) != (
                req.merchant, amount_cents, req.currency.upper()):
            raise HTTPException(409, "Idempotency key reused with a different request")
        return to_out(db, existing)

    with _DECIDE_LOCK:
        payment = Payment(
            agent_id=agent.id, idempotency_key=req.idempotency_key, merchant=req.merchant,
            amount_cents=amount_cents, currency=req.currency.upper(), purpose=req.purpose,
            user_goal=req.user_goal, context=req.context, state="PROPOSED",
        )
        db.add(payment)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Duplicate request in flight")
        audit(db, payment, "proposed", "agent",
              {"merchant": req.merchant, "amount": str(req.amount), "purpose": req.purpose})

        decision = decide(db, agent, merchant=req.merchant, amount_cents=amount_cents,
                          currency=req.currency, purpose=req.purpose,
                          user_goal=req.user_goal, context=req.context)
        payment.reasons, payment.risk_score = decision.reasons, decision.risk
        audit(db, payment, "policy_check", "system", {"checks": decision.checks})
        transition(db, payment, decision.state, "system", {"reasons": decision.reasons})
        db.commit()

    if payment.state == "APPROVED":
        executor.execute(db, payment, paypal)
        db.commit()
    return to_out(db, payment)


@router.get("/payments", response_model=list[PaymentOut], dependencies=[Depends(require_admin)])
def list_payments(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.execute(select(Payment).order_by(Payment.created_at.desc()).limit(min(limit, 500))).scalars()
    return [to_out(db, p) for p in rows]


@router.post("/payments/sync-all", dependencies=[Depends(require_admin)])
def sync_all(db: Session = Depends(get_db), paypal=Depends(get_paypal)):
    rows = db.execute(select(Payment).where(Payment.state == "ORDER_CREATED")).scalars().all()
    for p in rows:
        executor.sync(db, p, paypal)
    db.commit()
    return {"checked": len(rows)}


@router.get("/payments/{payment_id}", response_model=PaymentOut,
            dependencies=[Depends(require_admin)])
def get_payment(payment_id: str, db: Session = Depends(get_db)):
    return to_out(db, _get(db, payment_id), events=True)


@router.get("/my/payments/{payment_id}", response_model=PaymentOut)
def get_my_payment(payment_id: str, agent: Agent = Depends(current_agent),
                   db: Session = Depends(get_db)):
    """Agents can only read their own payments."""
    p = _get(db, payment_id)
    if p.agent_id != agent.id:
        raise HTTPException(404, "Payment not found")
    return to_out(db, p)


@router.post("/payments/{payment_id}/decision", response_model=PaymentOut,
             dependencies=[Depends(require_admin)])
def decide_payment(payment_id: str, body: DecisionRequest, db: Session = Depends(get_db),
                   paypal=Depends(get_paypal)):
    """Human-in-the-loop: approve or reject a payment that needs review."""
    p = _get(db, payment_id)
    if p.state != "PENDING_APPROVAL":
        raise HTTPException(409, f"Payment is {p.state}, not PENDING_APPROVAL")
    if body.decision == "reject":
        transition(db, p, "REJECTED", "admin", {"note": body.note})
        db.commit()
    else:
        transition(db, p, "APPROVED", "admin", {"note": body.note})
        db.commit()
        executor.execute(db, p, paypal, actor="admin")
        db.commit()
    return to_out(db, p)


@router.post("/payments/{payment_id}/sync", response_model=PaymentOut,
             dependencies=[Depends(require_admin)])
def sync_payment(payment_id: str, db: Session = Depends(get_db), paypal=Depends(get_paypal)):
    p = _get(db, payment_id)
    executor.sync(db, p, paypal)
    db.commit()
    return to_out(db, p)


@router.get("/agents", dependencies=[Depends(require_admin)])
def list_agents(db: Session = Depends(get_db)):
    now = utcnow()
    out = []
    for a in db.execute(select(Agent)).scalars():
        out.append({
            "id": a.id, "name": a.name, "status": a.status, "currency": a.currency,
            "max_per_txn": f"{a.max_per_txn_cents / 100:.2f}",
            "auto_approve_below": f"{a.auto_approve_below_cents / 100:.2f}",
            "daily_budget": f"{a.daily_budget_cents / 100:.2f}",
            "spent_today": f"{spent_today_cents(db, a.id, now) / 100:.2f}",
            "allowed_merchants": a.allowed_merchants,
        })
    return out
