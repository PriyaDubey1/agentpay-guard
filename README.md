# AgentPay Guard

> Let AI agents spend money through PayPal without ever holding the keys, with budgets, risk checks and human approval enforced on every payment.

**Status:** work in progress, built for the PayPal AI Hackathon 2026.

## The problem
AI agents are starting to make purchases on people's behalf, but nobody wants to hand an agent an open wallet. Agents can be tricked by prompt injection, retry and double-charge, or overspend.

## The idea
AgentPay Guard sits between any AI agent and PayPal. The agent can only *propose* payments. The Guard decides whether to allow, escalate to a human, or deny, then executes approved payments through the PayPal Sandbox.

## Planned features
- Policy engine: per-transaction limits, daily budgets, merchant allowlists
- Risk analysis: deterministic rules plus an LLM review (can only make decisions stricter, never looser)
- Human approval for risky or large payments
- Idempotent PayPal execution and signature-verified webhooks
- Full audit log and a dashboard
- Adversarial test suite with measured results

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env     # add your PayPal sandbox credentials
uvicorn app.main:app --reload
pytest
```

## Project layout
```
app/            FastAPI backend (api, core, models, services, schemas)
demo_agent/     Demo shopping agent that uses the Guard
attacks/        Adversarial test suite and results
dashboard/      Approval and monitoring UI
tests/          Unit and integration tests
docs/           Architecture notes
```

## License
MIT, see [LICENSE](LICENSE).
