"""Capture an order that was ALREADY approved in the browser.

Usage:
    python -m scripts.capture_order <ORDER_ID>
"""
import sys

from app.services.paypal_client import PayPalClient, PayPalError


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.capture_order <ORDER_ID>")
        return
    order_id = sys.argv[1]
    client = PayPalClient()
    try:
        order = client.get_order(order_id)
        print(f"order status: {order['status']}")
        if order["status"] == "COMPLETED":
            print("Already captured.")
            return
        if order["status"] != "APPROVED":
            print("Not approved yet, so it can't be captured.")
            return
        captured = client.capture_order(order_id, request_id=f"capture-{order_id}")
    except PayPalError as e:
        print(f"PayPal error: {e}")
        return
    print(f"status: {captured['status']}")
    print(f"capture id: {client.capture_id(captured)}")


if __name__ == "__main__":
    main()
