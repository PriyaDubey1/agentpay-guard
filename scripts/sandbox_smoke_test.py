"""Day-1 check: make ONE real payment in the PayPal Sandbox.

Run from the repo root (run it ALONE, don't paste other commands after it):
    python -m scripts.sandbox_smoke_test

Flow: create order -> you approve it in the browser as the sandbox buyer
-> the script notices the approval by itself (no typing needed)
-> captures the payment -> prints the capture id.
"""
import time
import uuid

from app.services.paypal_client import PayPalClient, PayPalError

WAIT_SECONDS = 600  # you get 10 minutes to finish the browser step


def wait_for_approval(client: PayPalClient, order_id: str) -> str:
    """Poll quietly; only print when the status changes."""
    deadline = time.time() + WAIT_SECONDS
    last = None
    while time.time() < deadline:
        status = client.get_order(order_id)["status"]
        if status != last:
            print(f"   order status: {status}")
            last = status
        if status in ("APPROVED", "COMPLETED", "VOIDED"):
            return status
        time.sleep(3)
    return last or "UNKNOWN"


def main() -> None:
    client = PayPalClient()
    run_id = uuid.uuid4().hex[:8]

    print("1) Creating order...")
    order = client.create_order(
        "10.00",
        "USD",
        reference_id=f"smoke-{run_id}",
        description="AgentPay Guard smoke test",
        request_id=f"create-smoke-{run_id}",
    )
    order_id = order["id"]
    print(f"   order id: {order_id}  status: {order['status']}")

    link = client.approval_link(order)
    print("\n2) Open this link in an incognito window, click LOG IN, use your")
    print("   SANDBOX BUYER account, then click Complete Purchase / Pay Now.")
    print("   You will land on an 'Example Domain' page: that means it worked.\n")
    print(f"   {link}\n")
    print(f"3) Waiting up to {WAIT_SECONDS // 60} minutes for your approval (no typing needed)...")

    status = wait_for_approval(client, order_id)
    if status != "APPROVED":
        print(f"\n   Order ended as '{status}', so it can't be captured.")
        print("   Re-run the script and finish the payment in the browser.")
        return

    print("\n4) Capturing...")
    try:
        captured = client.capture_order(order_id, request_id=f"capture-{order_id}")
    except PayPalError as e:
        print(f"   Capture failed: {e}")
        return
    print(f"   status: {captured['status']}")
    print(f"   capture id: {client.capture_id(captured)}")
    print("\nSuccess! The $10 sandbox payment is complete.")


if __name__ == "__main__":
    main()
