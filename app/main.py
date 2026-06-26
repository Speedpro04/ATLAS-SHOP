"""API FastAPI da Solara — recebe o webhook da Evolution e enfileira o trabalho.

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
logger = logging.getLogger("solara.api")

app = FastAPI(title="Solara — Vendedora Digital Yachts Atlas", version="1.0.0")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    """Página inicial = painel de vendas da Solara."""
    return FileResponse(_DASHBOARD_HTML, media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(_STATIC_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/status")
def status() -> dict[str, str]:
    return {"service": "solara", "status": "ok"}


@app.get("/health")
def health() -> JSONResponse:
    ok = memory.ping()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "redis": ok},
    )


@app.get("/dashboard")
def dashboard() -> FileResponse:
    """Painel de vendas da Solara (HTML)."""
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
    # --- Autenticação ---
    if not _authorized(token, apikey):
        logger.warning("⛔ Webhook recebido mas NÃO AUTORIZADO (token=%s, apikey=%s)", token, apikey)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    # --- Parse do body ---
    try:
        payload = await request.json()
    except (ValueError, TypeError):
        logger.warning("⛔ Webhook com JSON inválido")
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    # Log do evento recebido (resumo, sem dados sensíveis)
    event = payload.get("event", "sem_evento")
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    key = data.get("key") or {} if isinstance(data, dict) else {}
    remote_jid = key.get("remoteJid", "?") if isinstance(key, dict) else "?"
    from_me = key.get("fromMe", "?") if isinstance(key, dict) else "?"

    logger.info(
        "📩 Webhook recebido: event=%s | jid=%s | fromMe=%s | instance=%s",
        event, remote_jid, from_me, payload.get("instance", "?"),
    )

    # --- Parse para IncomingMessage ---
    msg = parse_webhook(payload)
    if msg is None or not msg.has_content:
        # Evento que não nos interessa (status, grupo, própria msg, etc.)
        logger.info("⏭️ Evento ignorado (msg=%s, has_content=%s)", msg is not None, getattr(msg, "has_content", False))
        return JSONResponse(status_code=200, content={"ignored": True})

    logger.info(
        "✅ Mensagem aceita: phone=%s | push_name=%s | text=%s | audio=%s",
        msg.phone,
        msg.push_name,
        (msg.text[:80] + "...") if msg.text and len(msg.text) > 80 else msg.text,
        bool(msg.audio_base64),
    )

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
    logger.info("📤 Mensagem enfileirada no Celery para %s", msg.phone)
    return JSONResponse(status_code=200, content={"queued": True})
