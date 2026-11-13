# AgentPay Guard

> Let AI agents spend money through PayPal without ever holding the keys: budgets, risk checks and human approval enforced on every payment.

Built for the **PayPal AI Hackathon 2026**. Runs entirely on the **PayPal Sandbox**.

## The problem
AI agents are starting to make purchases for people, but nobody wants to hand an agent an open wallet. An agent can be tricked by a poisoned web page (prompt injection), retry and double-charge, or be talked into overspending.

## What it does
AgentPay Guard sits between an AI agent and PayPal. The agent never sees PayPal credentials. It can only **propose** a payment. The Guard decides:

| Outcome | When | What happens |
|---|---|---|
| **Denied** | Breaks a hard rule: over the limit, unknown merchant, blocked category, prompt injection, over budget, wrong currency, suspended agent | No PayPal call is ever made |
| **Needs approval** | Above the auto-approve amount, looks like a split payment, or the LLM review objects | Waits in the dashboard for a human |
| **Approved** | Small and clean | Creates a real PayPal order |

Even approved payments are only **captured after the buyer approves inside PayPal**. The Guard polls PayPal and never captures early.

## How it works
```
 AI agent --POST /v1/payments--> [ idempotency -> hard rules -> budget/split checks -> LLM review ]
                                                      |
                     DENIED  <--------  decision  -------->  PENDING_APPROVAL --(human)--> APPROVED
                                                                                              |
                                                          PayPal Orders v2: create (idempotent) -> buyer approves -> capture
```
- **Hard rules are deterministic and always win.** The optional LLM review can only make a decision *stricter*, never looser, and it fails closed (an LLM outage escalates to a human, it never auto-approves).
- **State machine:** `PROPOSED -> DENIED | PENDING_APPROVAL | APPROVED -> ORDER_CREATED -> CAPTURED | FAILED`. Every change goes through one function and is written to an append-only audit log.
- **PayPal:** OAuth, Orders v2 create/get/capture, and a refund helper. Every money-moving call carries a `PayPal-Request-Id`, so retries cannot create duplicate orders or captures.
- **Race safety:** decision + insert are serialised, so two simultaneous requests cannot both squeeze under the daily budget.

## AI and tools used
- **PayPal Sandbox**: Orders v2 API for order creation and capture.
- **LLM goal-consistency review (optional)**: set `LLM_API_KEY` and `LLM_MODEL` (Anthropic Messages API). It receives the user's goal and the agent's proposal (agent text and page content are wrapped as untrusted data) and returns a risk score. Without a key this step is skipped and clearly shown as "skipped" in the audit trail.
- FastAPI, SQLAlchemy (SQLite), plain HTML/JS dashboard.

## Run it
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # add PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (sandbox) and change ADMIN_KEY
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 for the dashboard (admin key = `ADMIN_KEY`, default `admin-demo-key`).

In a second terminal, run the demo agent:
```bash
python -m demo_agent.agent
```
It proposes five payments: one small and legitimate, one that needs approval, and three attacks. For payments that reach PayPal, open the printed link, log in with a **US sandbox personal account**, and click **Complete Purchase**. The dashboard detects the approval and captures the payment automatically.

The demo agent's API key is `demo-agent-key` (created automatically on first start; demo only).

## Tests and attack results
```bash
pytest                    # unit tests + the whole adversarial suite
python -m attacks.run     # prints results and rewrites attacks/RESULTS.md
```
See [attacks/RESULTS.md](attacks/RESULTS.md). The suite covers prompt injection in the purpose field and in scraped page text, over-limit and oversized amounts, unknown merchants, blocked categories, split payments, budget exhaustion, replayed and conflicting idempotency keys, a suspended agent, wrong currency, negative and sub-cent amounts, a bad API key, an agent approving its own payment, and capturing before the buyer approved.

**Honest caveats.** The scenarios were written by the author against the author's own rules, so a 100% score shows the rules behave as designed, not that the system is unbreakable. The suite runs against a fake PayPal that mimics idempotency and refuses early capture. The real sandbox flow was verified separately (create, buyer approval, capture).

## Known limitations
- Webhooks are not implemented; the Guard polls PayPal for order status instead.
- Policy is edited in the database/seed, not in the UI. One agent is seeded.
- Injection detection is pattern-based plus the optional LLM review; a determined attacker could phrase around the patterns.
- The dashboard uses a shared admin key; there are no per-user accounts.
- Free-tier hosting on Render uses an ephemeral disk, so SQLite resets on redeploy. Use Postgres for anything real.
- Sandbox only. Do not use live credentials.

## Project layout
```
app/api/        FastAPI routes + auth dependencies
app/services/   policy engine, risk checks, state machine, PayPal client, executor
app/static/     dashboard (single HTML file)
attacks/        adversarial scenarios, runner, RESULTS.md
demo_agent/     demo agent that talks to the Guard over HTTP
tests/          unit + attack-suite tests
```

## License
MIT, see [LICENSE](LICENSE).
