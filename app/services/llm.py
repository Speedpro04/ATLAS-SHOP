"""Cérebro da Vega — GPT-5-mini via OpenAI.

Monta a conversa (system prompt + perfil + histórico + mensagem nova) e
devolve a resposta em texto. Falha de forma segura: se a API cair, devolve uma
mensagem neutra para o lead em vez de derrubar o worker.
"""

from __future__ import annotations

import logging

from openai import OpenAI

from app.config import settings

logger = logging.getLogger("vega.llm")

_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

FALLBACK_REPLY = (
    "Tive uma pequena instabilidade aqui do meu lado 🌊 Pode me mandar de novo? "
    "Se preferir, já posso te encaixar numa conversa rápida de 15 min com o Marcos, "
    "o fundador."
)


def _profile_note(profile: dict[str, str]) -> str | None:
    if not profile:
        return None
    pairs = [f"{k}: {v}" for k, v in profile.items()]
    return "Contexto conhecido do lead (use, não pergunte de novo): " + "; ".join(pairs)


def generate_reply(
    history: list[dict[str, str]],
    user_message: str,
    profile: dict[str, str] | None = None,
) -> str:
    """Gera a resposta da Vega para a mensagem do lead."""
    if _client is None:
        logger.error("OPENAI_API_KEY ausente — usando fallback.")
        return FALLBACK_REPLY

    messages: list[dict[str, str]] = [
        {"role": "system", "content": settings.system_prompt}
    ]
    note = _profile_note(profile or {})
    if note:
        messages.append({"role": "system", "content": note})
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    kwargs: dict = {
        "model": settings.openai_model,
        "messages": messages,
        "max_completion_tokens": settings.openai_max_output_tokens,
    }
    if settings.openai_temperature is not None:
        kwargs["temperature"] = settings.openai_temperature
    # Controla o raciocínio dos modelos gpt-5 (via extra_body p/ compatibilidade do SDK),
    # senão o raciocínio consome todo o orçamento de tokens e a resposta volta vazia.
    if settings.openai_model.startswith("gpt-5") and settings.openai_reasoning_effort:
        kwargs["extra_body"] = {"reasoning_effort": settings.openai_reasoning_effort}

    try:
        resp = _client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            logger.warning(
                "Resposta vazia do modelo (finish_reason=%s, usage=%s) — usando fallback.",
                getattr(choice, "finish_reason", "?"), getattr(resp, "usage", "?"),
            )
        return text or FALLBACK_REPLY
    except TypeError:
        # SDKs/modelos mais antigos usam max_tokens em vez de max_completion_tokens
        kwargs.pop("max_completion_tokens", None)
        kwargs["max_tokens"] = settings.openai_max_output_tokens
        try:
            resp = _client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip() or FALLBACK_REPLY
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao chamar o modelo (retry).")
            return FALLBACK_REPLY
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao chamar o modelo.")
        return FALLBACK_REPLY
