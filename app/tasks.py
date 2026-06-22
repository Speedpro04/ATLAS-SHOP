"""Tasks do Celery — onde a Vega de fato pensa e responde.

Fluxo de process_message:
  1. Se veio áudio -> OmniVoice STT transcreve.
  2. Carrega histórico + perfil do lead (Redis).
  3. GPT-5-mini gera a resposta (persona Vega + SPIN).
  4. Salva no histórico.
  5. Envia texto pela Evolution; se for curta e sem preço/link, também manda áudio.
"""

from __future__ import annotations

import logging
import re

from app import memory
from app.celery_app import celery_app
from app.config import settings
from app.services import evolution, llm, supabase_db, voice

logger = logging.getLogger("vega.tasks")

# Padrões que NÃO devem ir em áudio (precisam ser lidos/clicados)
_NO_AUDIO = re.compile(r"(https?://|www\.|US\$|R\$|@|\b\d{2,}\b)", re.IGNORECASE)


def _should_send_audio(text: str) -> bool:
    if not settings.voice_reply_enabled:
        return False
    if len(text) > settings.voice_reply_max_chars:
        return False
    if _NO_AUDIO.search(text):
        return False
    return True


@celery_app.task(name="vega.process_message", bind=True, max_retries=2)
def process_message(self, msg: dict) -> str:
    """Processa uma mensagem recebida. `msg` é o IncomingMessage serializado."""
    phone = msg["phone"]
    push_name = msg.get("push_name") or ""

    # 1) Resolve o texto (transcreve áudio se preciso)
    user_text = (msg.get("text") or "").strip()
    if not user_text and msg.get("audio_base64"):
        evolution.presence(phone, "recording")
        user_text = voice.transcribe(msg["audio_base64"]) or ""

    if not user_text:
        evolution.send_text(
            phone,
            "Não consegui ouvir/entender sua última mensagem 🌊 Pode me mandar "
            "por texto, por favor?",
        )
        return "empty"

    # 2) Contexto
    if push_name:
        memory.update_profile(phone, nome=push_name)
    profile = memory.get_profile(phone)
    history = memory.get_history(phone)

    # 3) Cérebro
    evolution.presence(phone, "composing")
    reply = llm.generate_reply(history=history, user_message=user_text, profile=profile)

    # 4) Persiste (Redis = memória de curto prazo; Supabase = registro permanente)
    memory.append_message(phone, "user", user_text)
    memory.append_message(phone, "assistant", reply)

    lead_id = supabase_db.upsert_lead(phone, nome=push_name or None)
    canal_in = "audio" if (not msg.get("text") and msg.get("audio_base64")) else "texto"
    supabase_db.log_message(phone, "user", user_text, canal=canal_in, lead_id=lead_id)
    supabase_db.log_message(phone, "assistant", reply, canal="texto", lead_id=lead_id)

    # 5) Entrega numa task separada: só o ENVIO é repetido se a Evolution falhar,
    #    sem re-chamar o GPT nem regravar os registros (evita duplicação/custo).
    deliver_reply.delay({"phone": phone, "text": reply})

    logger.info("Respondido %s (%d chars)", phone, len(reply))
    return "ok"


@celery_app.task(name="vega.deliver_reply", bind=True, max_retries=3, default_retry_delay=10)
def deliver_reply(self, payload: dict) -> str:
    """Envia a resposta pelo WhatsApp (texto sempre; áudio quando fizer sentido).
    Retentativa só do envio — o cérebro e os registros já rodaram uma vez."""
    phone = payload["phone"]
    text = payload["text"]

    if not evolution.send_text(phone, text):
        raise self.retry()

    if _should_send_audio(text):
        audio_b64 = voice.synthesize(text)
        if audio_b64:
            evolution.send_audio(phone, audio_b64)

    return "ok"
