import json

import httpx
import pytest

from app.services.paypal_client import PayPalClient, PayPalError


def make_client(handler):
    return PayPalClient(client_id="id", client_secret="secret",
                        base_url="https://api-m.sandbox.paypal.com",
                        transport=httpx.MockTransport(handler))


def test_token_cached_and_idempotency_header_sent():
    calls = {"token": 0}
    seen = {}

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        seen["request_id"] = request.headers.get("PayPal-Request-Id")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "O1", "status": "PAYER_ACTION_REQUIRED",
                                         "links": [{"rel": "payer-action", "href": "https://p/approve"}]})

    c = make_client(handler)
    o1 = c.create_order("10", "USD", reference_id="p1", request_id="create-p1")
    c.create_order("5.5", "USD", reference_id="p2", request_id="create-p2")
    assert calls["token"] == 1
    assert seen["request_id"] == "create-p2"
    assert seen["body"]["purchase_units"][0]["amount"]["value"] == "5.50"
    assert c.approval_link(o1) == "https://p/approve"


def test_error_response_raises():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY"})

    with pytest.raises(PayPalError) as exc:
        make_client(handler).capture_order("X", request_id="capture-X")
    assert exc.value.status_code == 422


def test_capture_id_extraction():
    assert PayPalClient.capture_id({"purchase_units": [{"payments": {"captures": [{"id": "C1"}]}}]}) == "C1"
    assert PayPalClient.capture_id({}) is None


def test_missing_credentials_message():
    c = PayPalClient(client_id="", client_secret="",
                     transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(RuntimeError, match="credentials missing"):
        c.get_order("X")
