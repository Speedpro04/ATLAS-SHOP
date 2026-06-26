"""Modelos do payload do webhook da Evolution API + extração da mensagem.

A Evolution manda muitos eventos; só nos interessa `messages.upsert` de
mensagens recebidas (fromMe=false). O formato pode variar entre versões, por
isso fazemos parsing defensivo e tolerante.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IncomingMessage:
    """Mensagem normalizada vinda do WhatsApp."""

    instance: str
    remote_jid: str          # ex.: 5512991187251@s.whatsapp.net
    phone: str               # só os dígitos: 5512991187251
    push_name: str           # nome exibido no WhatsApp
    text: str | None         # texto, quando houver
    audio_base64: str | None  # áudio em base64, quando houver
    message_id: str | None
    from_me: bool

    @property
    def has_content(self) -> bool:
        return bool(self.text) or bool(self.audio_base64)


def _jid_to_phone(jid: str) -> str:
    return jid.split("@", 1)[0].split(":", 1)[0] if jid else ""


def parse_webhook(payload: dict[str, Any]) -> IncomingMessage | None:
    """Converte o payload bruto da Evolution numa IncomingMessage.

    Retorna None se o evento não for uma mensagem de texto/áudio recebida.
    """
    event = (payload.get("event") or "").lower().replace("_", ".")
    # Aceitar variações da Evolution: messages.upsert, message, messages_upsert, etc.
    # Rejeitar apenas eventos que claramente NÃO são mensagens (ex: connection.update, qrcode)
    if event and "message" not in event:
        return None

    data = payload.get("data") or {}
    # Alguns formatos mandam uma lista em data; pega o primeiro.
    if isinstance(data, list):
        data = data[0] if data else {}

    key = data.get("key") or {}
    from_me = bool(key.get("fromMe", False))
    if from_me:
        return None  # ignora as próprias mensagens

    remote_jid = key.get("remoteJid") or ""
    # Ignora grupos e status/broadcast
    if remote_jid.endswith("@g.us") or remote_jid == "status@broadcast":
        return None

    message = data.get("message") or {}
    text: str | None = None
    audio_b64: str | None = None

    # Texto
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or None
    )

    # Áudio (PTT/voz). A Evolution pode anexar base64 conforme configuração.
    audio_msg = message.get("audioMessage")
    if audio_msg:
        audio_b64 = (
            data.get("base64")
            or message.get("base64")
            or audio_msg.get("base64")
            or None
        )

    msg = IncomingMessage(
        instance=payload.get("instance") or "",
        remote_jid=remote_jid,
        phone=_jid_to_phone(remote_jid),
        push_name=data.get("pushName") or "",
        text=text.strip() if isinstance(text, str) else None,
        audio_base64=audio_b64,
        message_id=key.get("id"),
        from_me=from_me,
    )

    if not msg.remote_jid or not (msg.text or msg.audio_base64):
        # Áudio sem base64 também chega aqui: ainda assim retornamos para a
        # task tentar baixar a mídia pela Evolution.
        if audio_msg and msg.remote_jid:
            return msg
        return None

    return msg
