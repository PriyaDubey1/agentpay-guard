"""Executes approved payments against PayPal and tracks their outcome."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.tables import Payment
from app.services.state import audit, transition


def _amount(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def execute(db: Session, payment: Payment, paypal, actor: str = "system") -> None:
    """APPROVED -> ORDER_CREATED (buyer must still approve inside PayPal)."""
    try:
        order = paypal.create_order(
            _amount(payment.amount_cents), payment.currency,
            reference_id=payment.id, description=payment.purpose,
            request_id=f"create-{payment.id}",   # idempotent: retries can't double-create
        )
    except Exception as e:
        payment.error = str(e)[:500]
        transition(db, payment, "FAILED", actor, {"stage": "create_order", "error": payment.error})
        return
    payment.paypal_order_id = order["id"]
    payment.approval_url = paypal.approval_link(order)
    transition(db, payment, "ORDER_CREATED", actor,
               {"paypal_order_id": order["id"], "paypal_status": order.get("status")})


def sync(db: Session, payment: Payment, paypal) -> Payment:
    """Check PayPal; capture only once the buyer has approved. Idempotent."""
    if payment.state != "ORDER_CREATED" or not payment.paypal_order_id:
        return payment
    try:
        order = paypal.get_order(payment.paypal_order_id)
        status = order.get("status")
        if status == "APPROVED":
            captured = paypal.capture_order(
                payment.paypal_order_id, request_id=f"capture-{payment.paypal_order_id}")
            if captured.get("status") == "COMPLETED":
                payment.paypal_capture_id = paypal.capture_id(captured)
                transition(db, payment, "CAPTURED", "paypal",
                           {"capture_id": payment.paypal_capture_id})
            else:
                audit(db, payment, "paypal_status", "paypal", {"status": captured.get("status")})
        elif status == "COMPLETED":
            payment.paypal_capture_id = paypal.capture_id(order)
            transition(db, payment, "CAPTURED", "paypal", {"capture_id": payment.paypal_capture_id})
        elif status == "VOIDED":
            payment.error = "Order voided at PayPal"
            transition(db, payment, "FAILED", "paypal", {"status": status})
    except Exception as e:
        audit(db, payment, "sync_error", "system", {"error": str(e)[:300]})
    return payment
