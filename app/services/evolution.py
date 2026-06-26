"""Cliente da Evolution API — envia texto e áudio pelo WhatsApp e baixa mídia.

Endpoints (Evolution API v2):
  POST /message/sendText/{instance}            -> {number, text}
  POST /message/sendWhatsAppAudio/{instance}   -> {number, audio (base64)}
  POST /chat/getBase64FromMediaMessage/{instance} -> baixa mídia em base64
Autenticação por header "apikey".
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger("solara.evolution")

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _headers() -> dict[str, str]:
    return {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}


def _url(path: str) -> str:
    base = settings.evolution_base_url.rstrip("/")
    instance = settings.evolution_instance
    return f"{base}{path}/{instance}"


def send_text(phone: str, text: str) -> bool:
    """Envia mensagem de texto. `phone` são só os dígitos (ex.: 5512...)."""
    payload = {"number": phone, "text": text}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(_url("/message/sendText"), json=payload, headers=_headers())
            r.raise_for_status()
            return True
    except httpx.HTTPError:
        logger.exception("Falha ao enviar texto para %s", phone)
        return False


def send_audio(phone: str, audio_base64: str) -> bool:
    """Envia um áudio (PTT) a partir de base64 (saída do OmniVoice TTS)."""
    payload = {"number": phone, "audio": audio_base64}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(
                _url("/message/sendWhatsAppAudio"), json=payload, headers=_headers()
            )
            r.raise_for_status()
            return True
    except httpx.HTTPError:
        logger.exception("Falha ao enviar áudio para %s", phone)
        return False


def fetch_media_base64(message: dict) -> str | None:
    """Baixa a mídia (áudio) de uma mensagem como base64, quando o webhook não
    trouxe o base64 embutido. `message` é o objeto bruto data.message/key.
    """
    payload = {"message": message, "convertToMp4": False}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(
                _url("/chat/getBase64FromMediaMessage"),
                json=payload,
                headers=_headers(),
            )
            r.raise_for_status()
            data = r.json()
            return data.get("base64") or (data.get("media") or {}).get("base64")
    except (httpx.HTTPError, ValueError):
        logger.exception("Falha ao baixar mídia")
        return None


def presence(phone: str, state: str = "composing") -> None:
    """Mostra 'digitando...' para deixar a conversa mais humana (best-effort)."""
    payload = {"number": phone, "presence": state, "delay": 1200}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            client.post(_url("/chat/sendPresence"), json=payload, headers=_headers())
    except httpx.HTTPError:
        pass
