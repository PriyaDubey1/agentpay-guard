"""Thin PayPal REST client (Sandbox/Live) for Orders v2 and refunds.

- Every money-moving POST carries a PayPal-Request-Id header, so retries
  can never create duplicate orders/captures.
- The OAuth token is cached until shortly before it expires.
- A custom httpx transport can be injected, which keeps tests offline.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings


class PayPalError(Exception):
    """Raised when PayPal returns a non-2xx response."""

    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"PayPal API error {status_code}: {body}")


def _money(amount: Decimal | str | float) -> str:
    return f"{Decimal(str(amount)):.2f}"


class PayPalClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ):
        self.client_id = settings.paypal_client_id if client_id is None else client_id
        self.client_secret = (
            settings.paypal_client_secret if client_secret is None else client_secret
        )
        self.base_url = (base_url or settings.paypal_api_base).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url, transport=transport, timeout=timeout
        )
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "PayPal credentials missing. Set PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET in your .env file."
            )
        r = self._http.post(
            "/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        data = self._parse(r)
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 300))
        return self._token

    @staticmethod
    def _parse(r: httpx.Response) -> dict:
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {"raw": r.text}
        if r.status_code >= 400:
            raise PayPalError(r.status_code, body)
        return body

    def _request(self, method: str, path: str, *, json: dict | None = None,
                 request_id: str | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        r = self._http.request(method, path, headers=headers, json=json)
        return self._parse(r)

    def create_order(self, amount, currency: str, *, reference_id: str,
                     description: str = "", request_id: str,
                     return_url: str = "https://example.com/return",
                     cancel_url: str = "https://example.com/cancel") -> dict:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": _money(amount)},
            }],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "user_action": "PAY_NOW",
            }}},
        }
        return self._request("POST", "/v2/checkout/orders", json=body, request_id=request_id)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str, *, request_id: str) -> dict:
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture",
                             json={}, request_id=request_id)

    def refund_capture(self, capture_id: str, *, request_id: str, amount=None,
                       currency: str | None = None, note: str = "") -> dict:
        body: dict[str, Any] = {}
        if amount is not None:
            body["amount"] = {"value": _money(amount), "currency_code": currency}
        if note:
            body["note_to_payer"] = note[:255]
        return self._request("POST", f"/v2/payments/captures/{capture_id}/refund",
                             json=body, request_id=request_id)

    @staticmethod
    def approval_link(order: dict) -> str | None:
        for link in order.get("links", []):
            if link.get("rel") in ("payer-action", "approve"):
                return link["href"]
        return None

    @staticmethod
    def capture_id(captured_order: dict) -> str | None:
        try:
            return captured_order["purchase_units"][0]["payments"]["captures"][0]["id"]
        except (KeyError, IndexError):
            return None

    def close(self) -> None:
        self._http.close()
