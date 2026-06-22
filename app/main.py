"""API FastAPI da Vega — recebe o webhook da Evolution e enfileira o trabalho.

O webhook responde rápido (200) e joga o processamento para o Celery, para o
WhatsApp nunca esperar pela IA. Validação simples por token.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import memory
from app.config import settings
from app.schemas import parse_webhook
from app.services import supabase_db
from app.tasks import process_message

_DASHBOARD_HTML = Path(__file__).resolve().parent / "static" / "dashboard.html"

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("vega.api")

app = FastAPI(title="Vega — Vendedora Digital Yachts Atlas", version="1.0.0")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    """Página inicial = painel de vendas da Vega."""
    return FileResponse(_DASHBOARD_HTML, media_type="text/html")


@app.get("/status")
def status() -> dict[str, str]:
    return {"service": "vega", "status": "ok"}


@app.get("/health")
def health() -> JSONResponse:
    ok = memory.ping()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "redis": ok},
    )


@app.get("/dashboard")
def dashboard() -> FileResponse:
    """Painel de vendas da Vega (HTML)."""
    return FileResponse(_DASHBOARD_HTML, media_type="text/html")


@app.get("/api/dashboard/stats")
def dashboard_stats() -> JSONResponse:
    """Dados do painel (KPIs, funil e atividade recente) — lidos do Supabase."""
    return JSONResponse(content=supabase_db.dashboard_stats())


def _authorized(token_q: str | None, apikey: str | None) -> bool:
    expected = settings.webhook_token
    if not expected:
        return True  # sem token configurado, não bloqueia (dev)
    return token_q == expected or apikey == expected


@app.post("/webhook/evolution")
async def evolution_webhook(
    request: Request,
    token: str | None = Query(default=None),
    apikey: str | None = Header(default=None),
) -> JSONResponse:
    if not _authorized(token, apikey):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    try:
        payload = await request.json()
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    msg = parse_webhook(payload)
    if msg is None or not msg.has_content:
        # Evento que não nos interessa (status, grupo, própria msg, etc.)
        return JSONResponse(status_code=200, content={"ignored": True})

    # Enfileira no Celery e responde já
    process_message.delay(
        {
            "instance": msg.instance,
            "remote_jid": msg.remote_jid,
            "phone": msg.phone,
            "push_name": msg.push_name,
            "text": msg.text,
            "audio_base64": msg.audio_base64,
            "message_id": msg.message_id,
        }
    )
    return JSONResponse(status_code=200, content={"queued": True})
