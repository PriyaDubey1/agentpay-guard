"""In-memory stand-in for PayPalClient used by tests and the attack suite.

It mimics the behaviours that matter: idempotent order creation by
request id, and capture being refused until the buyer has approved.
"""
from app.services.paypal_client import PayPalClient, PayPalError


class FakePayPal:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self._by_request: dict[str, str] = {}
        self.create_calls = 0       # distinct orders actually created
        self.capture_calls = 0

    def create_order(self, amount, currency, *, reference_id, description="",
                     request_id, **_) -> dict:
        if request_id in self._by_request:
            return self._view(self._by_request[request_id])
        self.create_calls += 1
        oid = f"FAKE{self.create_calls:04d}"
        self.orders[oid] = {"id": oid, "status": "PAYER_ACTION_REQUIRED",
                            "amount": str(amount), "currency": currency, "capture": None}
        self._by_request[request_id] = oid
        return self._view(oid)

    def _view(self, oid: str) -> dict:
        o = self.orders[oid]
        view = {"id": oid, "status": o["status"],
                "links": [{"rel": "payer-action",
                           "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]}
        if o["capture"]:
            view["purchase_units"] = [{"payments": {"captures": [{"id": o["capture"]}]}}]
        return view

    def get_order(self, order_id: str) -> dict:
        return self._view(order_id)

    def approve(self, order_id: str) -> None:
        """Simulate the buyer clicking 'Complete Purchase'."""
        self.orders[order_id]["status"] = "APPROVED"

    def capture_order(self, order_id: str, *, request_id: str) -> dict:
        self.capture_calls += 1
        o = self.orders[order_id]
        if o["status"] == "COMPLETED":
            return self._view(order_id)
        if o["status"] != "APPROVED":
            raise PayPalError(422, {"details": [{"issue": "ORDER_NOT_APPROVED"}]})
        o["status"], o["capture"] = "COMPLETED", f"CAP{order_id}"
        return self._view(order_id)

    approval_link = staticmethod(PayPalClient.approval_link)
    capture_id = staticmethod(PayPalClient.capture_id)
