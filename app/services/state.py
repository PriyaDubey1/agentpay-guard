"""Payment state machine. Every state change goes through transition()."""
from sqlalchemy.orm import Session

from app.models.tables import AuditEvent, Payment

ALLOWED: dict[str, set[str]] = {
    "PROPOSED": {"DENIED", "PENDING_APPROVAL", "APPROVED"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
    "APPROVED": {"ORDER_CREATED", "FAILED"},
    "ORDER_CREATED": {"CAPTURED", "FAILED"},
}
TERMINAL = {"DENIED", "REJECTED", "CAPTURED", "FAILED"}
# States that count against budgets (money is committed or may be committed).
ACTIVE = {"PENDING_APPROVAL", "APPROVED", "ORDER_CREATED", "CAPTURED"}


class InvalidTransition(Exception):
    pass


def audit(db: Session, payment: Payment, event_type: str, actor: str,
          details: dict | None = None, from_state: str | None = None,
          to_state: str | None = None) -> None:
    db.add(AuditEvent(payment_id=payment.id, event_type=event_type, actor=actor,
                      details=details, from_state=from_state, to_state=to_state))


def transition(db: Session, payment: Payment, new_state: str, actor: str,
               details: dict | None = None) -> None:
    if new_state not in ALLOWED.get(payment.state, set()):
        raise InvalidTransition(f"{payment.state} -> {new_state} is not allowed")
    old = payment.state
    payment.state = new_state
    audit(db, payment, "state_change", actor, details, old, new_state)
