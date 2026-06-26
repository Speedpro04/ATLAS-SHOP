"""Cérebro da Solara — GPT-5-mini via OpenAI.

Monta a conversa (system prompt + perfil + histórico + mensagem nova) e
devolve a resposta em texto. Falha de forma segura: se a API cair, devolve uma
mensagem neutra para o lead em vez de derrubar o worker.
"""

from __future__ import annotations

import logging

from openai import OpenAI

from app.config import settings

logger = logging.getLogger("solara.llm")

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
    """Gera a resposta da Solara para a mensagem do lead."""
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

    logger.info(
        "Chamando %s (reasoning=%s, max_tokens=%d, msgs=%d)",
        settings.openai_model,
        settings.openai_reasoning_effort,
        settings.openai_max_output_tokens,
        len(messages),
    )

    kwargs: dict = {
        "model": settings.openai_model,
        "messages": messages,
        "max_completion_tokens": settings.openai_max_output_tokens,
    }
    if settings.openai_temperature is not None:
        kwargs["temperature"] = settings.openai_temperature

    # Modelos gpt-5 são de raciocínio: reasoning_effort controla o quanto
    # o modelo "pensa" antes de responder. Sem isso, o raciocínio pode
    # consumir TODO o orçamento de tokens e a resposta fica vazia.
    is_reasoning_model = any(
        settings.openai_model.startswith(p) for p in ("gpt-5", "o1", "o3", "o4")
    )
    if is_reasoning_model and settings.openai_reasoning_effort:
        kwargs["reasoning_effort"] = settings.openai_reasoning_effort

    try:
        resp = _client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()

        # Log detalhado para diagnóstico
        usage = getattr(resp, "usage", None)
        logger.info(
            "Resposta do modelo: finish_reason=%s, len=%d, usage=%s",
            getattr(choice, "finish_reason", "?"),
            len(text),
            (
                f"prompt={usage.prompt_tokens}/completion={usage.completion_tokens}/total={usage.total_tokens}"
                if usage
                else "?"
            ),
        )

        if not text:
            logger.warning(
                "⚠️ Resposta VAZIA do modelo! finish_reason=%s — "
                "Possível causa: reasoning consumiu todo o orçamento de tokens.",
                getattr(choice, "finish_reason", "?"),
            )
        return text or FALLBACK_REPLY

    except TypeError as exc:
        # SDKs/modelos mais antigos usam max_tokens em vez de max_completion_tokens
        logger.warning("TypeError na chamada (%s) — tentando com max_tokens...", exc)
        kwargs.pop("max_completion_tokens", None)
        kwargs.pop("reasoning_effort", None)
        kwargs["max_tokens"] = settings.openai_max_output_tokens
        try:
            resp = _client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            logger.info("Retry com max_tokens OK — len=%d", len(text))
            return text or FALLBACK_REPLY
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao chamar o modelo (retry com max_tokens).")
            return FALLBACK_REPLY

    except Exception:  # noqa: BLE001
        logger.exception("Falha ao chamar o modelo.")
        return FALLBACK_REPLY
