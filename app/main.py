from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import payments
from app.db import SessionLocal, init_db
from app.seed import ensure_demo_agent

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_demo_agent(db)
    yield


app = FastAPI(
    title="AgentPay Guard",
    description="A policy-enforced payment gateway for AI agents, built on PayPal.",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(payments.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html")
