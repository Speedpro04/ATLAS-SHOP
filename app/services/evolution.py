"""Cliente da Evolution API — envia texto e áudio pelo WhatsApp e baixa mídia.

Endpoints (Evolution API v2):
  POST /message/sendText/{instance}            -> {number, textMessage.text}
  POST /message/sendMedia/{instance}           -> multipart com áudio
  POST /chat/getBase64FromMediaMessage/{instance} -> baixa mídia em base64
Autenticação por header "apikey".
"""

from __future__ import annotations

import logging
from base64 import b64decode
from binascii import Error as B64Error

import httpx

from app.config import settings

logger = logging.getLogger("solara.evolution")

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _json_headers() -> dict[str, str]:
    return {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}


def _auth_headers() -> dict[str, str]:
    return {"apikey": settings.evolution_api_key}


def _url(path: str) -> str:
    base = settings.evolution_base_url.rstrip("/")
    instance = settings.evolution_instance
    return f"{base}{path}/{instance}"


def _post_json(path: str, payload: dict) -> httpx.Response:
    with httpx.Client(timeout=_TIMEOUT) as client:
        return client.post(_url(path), json=payload, headers=_json_headers())


def send_text(phone: str, text: str) -> bool:
    """Envia mensagem de texto. `phone` são só os dígitos (ex.: 5512...)."""
    payload = {"number": phone, "textMessage": {"text": text}}
    try:
        r = _post_json("/message/sendText", payload)
        r.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Falha ao enviar texto para %s", phone)
        return False


def send_audio(phone: str, audio_base64: str) -> bool:
    """Envia um áudio (PTT) a partir de base64 (saída do OmniVoice TTS)."""
    try:
        audio_bytes = b64decode(audio_base64, validate=True)
    except (B64Error, ValueError):
        logger.exception("Áudio base64 inválido para %s", phone)
        return False

    data = {"number": phone, "mediatype": "audio", "fileName": "solara-reply.ogg"}
    files = {"media": ("solara-reply.ogg", audio_bytes, "audio/ogg")}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(
                _url("/message/sendMedia"),
                data=data,
                files=files,
                headers=_auth_headers(),
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
                headers=_json_headers(),
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
            client.post(_url("/chat/sendPresence"), json=payload, headers=_json_headers())
    except httpx.HTTPError:
        pass
