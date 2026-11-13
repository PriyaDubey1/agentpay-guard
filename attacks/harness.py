"""Builds an isolated app (in-memory DB + fake PayPal) for each scenario."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_paypal
from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import tables  # noqa: F401
from app.models.tables import Agent
from app.seed import DEMO_API_KEY, ensure_demo_agent
from app.services.fake_paypal import FakePayPal


class Harness:
    def __init__(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            ensure_demo_agent(db)
        self.paypal = FakePayPal()

        def _db():
            s = self.Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_paypal] = lambda: self.paypal
        self.client = TestClient(app)
        self.agent_headers = {"X-API-Key": DEMO_API_KEY}
        self.admin_headers = {"X-Admin-Key": settings.admin_key}

    def close(self):
        app.dependency_overrides.clear()

    def propose(self, headers=None, **overrides):
        body = {
            "idempotency_key": uuid.uuid4().hex,
            "merchant": "acme-books",
            "amount": "10.00",
            "currency": "USD",
            "purpose": "Buy 'Clean Code' for the user",
            "user_goal": "Buy a programming book under $30",
        }
        body.update(overrides)
        return self.client.post("/v1/payments", json=body,
                                headers=self.agent_headers if headers is None else headers)

    def decide(self, payment_id, decision, headers=None):
        return self.client.post(f"/v1/payments/{payment_id}/decision", json={"decision": decision},
                                headers=self.admin_headers if headers is None else headers)

    def sync(self, payment_id):
        return self.client.post(f"/v1/payments/{payment_id}/sync", headers=self.admin_headers)

    def suspend_agent(self):
        with self.Session() as db:
            a = db.execute(select(Agent)).scalars().first()
            a.status = "suspended"
            db.commit()
