"""OmniVoice — STT (transcrever áudio do lead) e TTS (voz da Vega).

A API exata depende da sua conta OmniVoice. Concentramos as suposições aqui,
em duas funções simples, para você ajustar caminho/headers num só lugar:

  STT: POST {base}/v1/transcriptions   (multipart com o áudio)  -> {"text": "..."}
  TTS: POST {base}/v1/speech           (json com o texto)       -> bytes de áudio

Ambas falham de forma segura (retornam None) para não derrubar o fluxo: sem
STT, a Vega pede o texto; sem TTS, ela responde só em texto.
"""

from __future__ import annotations

import base64
import binascii
import logging

import httpx

from app.config import settings

logger = logging.getLogger("vega.voice")

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.omnivoice_api_key}"}


def transcribe(audio_base64: str) -> str | None:
    """Transcreve um áudio (base64) para texto. Retorna None em falha."""
    if not settings.omnivoice_base_url:
        return None
    try:
        audio_bytes = base64.b64decode(audio_base64)
    except (binascii.Error, ValueError):
        logger.warning("Áudio base64 inválido")
        return None

    url = f"{settings.omnivoice_base_url.rstrip('/')}/v1/transcriptions"
    files = {"file": ("audio.ogg", audio_bytes, "audio/ogg")}
    payload = {"language": settings.omnivoice_stt_language}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(url, headers=_headers(), data=payload, files=files)
            r.raise_for_status()
            text = (r.json().get("text") or "").strip()
            return text or None
    except (httpx.HTTPError, ValueError):
        logger.exception("Falha no STT (OmniVoice)")
        return None


def synthesize(text: str) -> str | None:
    """Converte texto em áudio. Retorna base64 do áudio, ou None em falha."""
    if not settings.omnivoice_base_url:
        return None
    url = f"{settings.omnivoice_base_url.rstrip('/')}/v1/speech"
    payload = {
        "voice": settings.omnivoice_tts_voice,
        "text": text,
        "format": "ogg",
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(url, headers=_headers(), json=payload)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "application/json" in ctype:
                # API que devolve base64 dentro de JSON
                data = r.json()
                return data.get("audio") or data.get("audio_base64")
            # API que devolve os bytes do áudio direto
            return base64.b64encode(r.content).decode("ascii")
    except (httpx.HTTPError, ValueError):
        logger.exception("Falha no TTS (OmniVoice)")
        return None
