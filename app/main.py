from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db.session import Base, engine
from app.routers import appointments, audit, billing, patients, practices, triage
from app.services.qdrant_client import ensure_collections


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    try:
        ensure_collections()
    except Exception as exc:  # noqa: BLE001
        # Don't crash app startup if Qdrant isn't reachable yet (e.g. first
        # `docker compose up` race); endpoints that need it will error clearly.
        print(f"[startup] Warning: could not reach Qdrant to ensure collections: {exc}")
    yield


app = FastAPI(
    title="practice-ops-agent",
    description="Vertical AI back-office assistant for solo/small medical & dental practices.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(practices.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(billing.router)
app.include_router(triage.router)
app.include_router(audit.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <html>
      <head><title>practice-ops-agent</title></head>
      <body style="font-family: sans-serif; max-width: 640px; margin: 40px auto;">
        <h1>practice-ops-agent</h1>
        <p>Backend is running. See <a href="/docs">/docs</a> for the interactive API,
        or <a href="/ui">/ui</a> for a minimal demo form.</p>
      </body>
    </html>
    """


app.mount("/ui", StaticFiles(directory="app/static", html=True), name="static")
