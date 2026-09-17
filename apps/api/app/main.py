from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import assistant, documents, notes, settings as settings_router, translate
from app.schemas import HealthOut
from app.services.lifecycle import (
    mark_leaving,
    shutdown_all,
    start_heartbeat_watcher,
    touch_heartbeat,
)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(translate.router)
app.include_router(notes.router)
app.include_router(assistant.router)
app.include_router(settings_router.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_heartbeat_watcher(enabled=settings.auto_shutdown)


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(app=settings.app_name)


@app.post("/api/heartbeat")
def heartbeat() -> dict[str, str]:
    touch_heartbeat()
    return {"status": "ok"}


@app.post("/api/leaving")
def leaving() -> dict[str, str]:
    """Tab closing/refreshing — short grace; heartbeat cancels if page comes back."""
    mark_leaving()
    return {"status": "leaving"}


@app.post("/api/shutdown")
def shutdown() -> dict[str, str]:
    """Optional hard stop."""
    shutdown_all("explicit shutdown")
    return {"status": "shutting_down"}
