from attacks.harness import Harness


def test_demo_run_and_reset():
    h = Harness()
    try:
        r = h.client.post("/v1/demo/run", headers=h.admin_headers)
        states = [p["state"] for p in r.json()]
        assert states.count("DENIED") == 3 and "PENDING_APPROVAL" in states and "ORDER_CREATED" in states
        assert h.client.post("/v1/demo/run").status_code == 401
        assert h.client.post("/v1/demo/reset", headers=h.admin_headers).json() == {"ok": True}
        assert h.client.get("/v1/payments", headers=h.admin_headers).json() == []
        r = h.client.post("/v1/demo/propose", headers=h.admin_headers,
                          json={"merchant": "acme-books", "amount": "5.00", "purpose": "Pen"})
        assert r.json()["state"] == "ORDER_CREATED"
    finally:
        h.close()
