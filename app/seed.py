from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Agent, hash_key

DEMO_API_KEY = "demo-agent-key"   # demo only; rotate for any real use


def ensure_demo_agent(db: Session) -> Agent:
    agent = db.execute(select(Agent)).scalars().first()
    if agent:
        return agent
    agent = Agent(
        name="demo-shopping-agent",
        api_key_hash=hash_key(DEMO_API_KEY),
        currency="USD",
        max_per_txn_cents=10_000,        # $100 per payment
        daily_budget_cents=20_000,       # $200 per day
        auto_approve_below_cents=2_500,  # <= $25 goes through without a human
        allowed_merchants=["acme-books", "acme-coffee", "acme-cloud"],
        blocked_keywords=["gift card", "crypto", "bitcoin", "wire transfer", "western union"],
    )
    db.add(agent)
    db.commit()
    return agent
