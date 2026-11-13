import hmac
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.tables import Agent, hash_key
from app.services.paypal_client import PayPalClient


@lru_cache
def _paypal() -> PayPalClient:
    return PayPalClient()


def get_paypal():
    return _paypal()


def current_agent(x_api_key: str | None = Header(default=None),
                  db: Session = Depends(get_db)) -> Agent:
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key")
    agent = db.execute(select(Agent).where(Agent.api_key_hash == hash_key(x_api_key))).scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid API key")
    return agent


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(401, "Admin key required")
