"""Memória de conversa por lead, guardada no Redis.

Cada lead (telefone) tem uma lista de mensagens no formato do chat do OpenAI:
{"role": "user"|"assistant", "content": "..."}. Guardamos também um pequeno
perfil (nome, marina, nº de barcos) que a Solara vai preenchendo via metadados.
"""

from __future__ import annotations

import json

import redis

from app.config import settings

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _history_key(phone: str) -> str:
    return f"solara:history:{phone}"


def _profile_key(phone: str) -> str:
    return f"solara:profile:{phone}"


def get_history(phone: str) -> list[dict[str, str]]:
    """Retorna o histórico recente (mais antigo -> mais novo)."""
    raw = _redis.lrange(_history_key(phone), -settings.history_max_messages, -1)
    out: list[dict[str, str]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except (ValueError, TypeError):
            continue
    return out


def append_message(phone: str, role: str, content: str) -> None:
    key = _history_key(phone)
    pipe = _redis.pipeline()
    pipe.rpush(key, json.dumps({"role": role, "content": content}))
    # Mantém a lista enxuta (guarda o dobro do que enviamos ao modelo)
    pipe.ltrim(key, -settings.history_max_messages * 2, -1)
    pipe.expire(key, settings.conversation_ttl)
    pipe.execute()


def get_profile(phone: str) -> dict[str, str]:
    return _redis.hgetall(_profile_key(phone)) or {}


def update_profile(phone: str, **fields: str) -> None:
    clean = {k: v for k, v in fields.items() if v}
    if not clean:
        return
    key = _profile_key(phone)
    _redis.hset(key, mapping=clean)
    _redis.expire(key, settings.conversation_ttl)


def reset(phone: str) -> None:
    _redis.delete(_history_key(phone), _profile_key(phone))


def ping() -> bool:
    try:
        return bool(_redis.ping())
    except redis.RedisError:
        return False
