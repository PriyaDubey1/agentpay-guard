from fastapi import FastAPI

app = FastAPI(
    title="AgentPay Guard",
    description="A policy-enforced payment gateway for AI agents, built on PayPal.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
