"""Decision pipeline: hard rules first, soft signals second.

Order: cheap deterministic checks -> budget/split checks -> optional LLM.
The LLM can only tighten the outcome. Hard rules always win.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import Agent, Payment, utcnow
from app.services import risk
from app.services.state import ACTIVE

SPLIT_WINDOW = timedelta(minutes=15)


@dataclass
class Decision:
    state: str                      # DENIED | PENDING_APPROVAL | APPROVED
    reasons: list[str] = field(default_factory=list)
    risk: int = 0
    checks: list[dict] = field(default_factory=list)


def dollars(cents: int) -> str:
    return f"{cents / 100:.2f}"


def spent_today_cents(db: Session, agent_id: str, now: datetime) -> int:
    start = datetime(now.year, now.month, now.day)
    q = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
        Payment.agent_id == agent_id,
        Payment.created_at >= start,
        Payment.state.in_(ACTIVE),
    )
    return int(db.execute(q).scalar_one())


def recent_merchant_cents(db: Session, agent_id: str, merchant: str, now: datetime) -> int:
    q = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
        Payment.agent_id == agent_id,
        func.lower(Payment.merchant) == merchant.lower(),
        Payment.created_at >= now - SPLIT_WINDOW,
        Payment.state.in_(ACTIVE),
    )
    return int(db.execute(q).scalar_one())


def decide(db: Session, agent: Agent, *, merchant: str, amount_cents: int, currency: str,
           purpose: str, user_goal: str | None, context: str | None,
           now: datetime | None = None, llm=risk.llm_review) -> Decision:
    now = now or utcnow()
    d = Decision(state="APPROVED")

    def deny(rule: str, reason: str, score: int = 100) -> Decision:
        d.state, d.risk = "DENIED", max(d.risk, score)
        d.reasons.append(reason)
        d.checks.append({"rule": rule, "result": "deny", "reason": reason})
        return d

    def passed(rule: str) -> None:
        d.checks.append({"rule": rule, "result": "pass"})

    # ---- hard rules (deterministic) ----
    if agent.status != "active":
        return deny("agent_status", "Agent is suspended")
    passed("agent_status")

    if currency.upper() != agent.currency:
        return deny("currency", f"Currency {currency} not allowed (policy: {agent.currency})")
    passed("currency")

    if amount_cents > agent.max_per_txn_cents:
        return deny("max_per_txn", f"Amount ${dollars(amount_cents)} exceeds per-transaction "
                                   f"limit ${dollars(agent.max_per_txn_cents)}")
    passed("max_per_txn")

    if agent.allowed_merchants is not None and merchant.lower() not in [
        m.lower() for m in agent.allowed_merchants
    ]:
        return deny("merchant_allowlist", f"Merchant '{merchant}' is not on the allowlist")
    passed("merchant_allowlist")

    haystack = f"{purpose} {merchant}".lower()
    for kw in agent.blocked_keywords or []:
        if kw.lower() in haystack:
            return deny("blocked_keyword", f"Blocked category/keyword: '{kw}'")
    passed("blocked_keyword")

    hits = risk.find_injection(purpose, context)
    if hits:
        return deny("prompt_injection", "Possible prompt injection in purpose/context text")
    passed("prompt_injection")

    spent = spent_today_cents(db, agent.id, now)
    if spent + amount_cents > agent.daily_budget_cents:
        return deny("daily_budget", f"Daily budget exceeded: ${dollars(spent)} already committed "
                                    f"+ ${dollars(amount_cents)} > ${dollars(agent.daily_budget_cents)}")
    passed("daily_budget")

    # ---- escalation rules (human must look) ----
    review = False
    if amount_cents > agent.auto_approve_below_cents:
        review = True
        d.risk = max(d.risk, 40)
        d.reasons.append(f"Amount ${dollars(amount_cents)} is above the auto-approve threshold "
                         f"(${dollars(agent.auto_approve_below_cents)})")
        d.checks.append({"rule": "auto_approve_threshold", "result": "review"})
    else:
        passed("auto_approve_threshold")

    window = recent_merchant_cents(db, agent.id, merchant, now)
    if window and window + amount_cents > agent.auto_approve_below_cents:
        review = True
        d.risk = max(d.risk, 60)
        d.reasons.append(f"Possible split payment: ${dollars(window)} already sent to this "
                         f"merchant in the last 15 min")
        d.checks.append({"rule": "split_detection", "result": "review"})
    else:
        passed("split_detection")

    # ---- optional LLM review (can only tighten) ----
    result = llm(user_goal=user_goal, purpose=purpose, merchant=merchant,
                 amount=dollars(amount_cents), currency=currency, context=context)
    if result is None:
        d.checks.append({"rule": "llm_review", "result": "skipped", "reason": "no LLM configured"})
    elif "error" in result:
        review = True
        d.risk = max(d.risk, 50)
        d.reasons.append("LLM review unavailable: escalated to a human (fail closed)")
        d.checks.append({"rule": "llm_review", "result": "error", "reason": result["error"]})
    else:
        score = result["score"]
        d.risk = max(d.risk, score)
        d.checks.append({"rule": "llm_review", "result": "ok", **result})
        if score >= 90:
            return deny("llm_review", "LLM review judged the payment inconsistent with the "
                                      "user's goal: " + "; ".join(result["reasons"]), score)
        if not result["consistent"] or score >= 60:
            review = True
            d.reasons.append("LLM review flagged: " + "; ".join(result["reasons"]))

    d.state = "PENDING_APPROVAL" if review else "APPROVED"
    if not d.reasons:
        d.reasons.append("All policy checks passed")
    return d
