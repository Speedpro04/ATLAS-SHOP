"""Configurações da Vega — lidas do ambiente (.env).

Secrets nunca entram no código: tudo vem de variáveis de ambiente.
Veja `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "prompts" / "vega_system_prompt.txt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "production"
    log_level: str = "INFO"
    webhook_token: str = "troque-este-token"

    # Redis / memória
    redis_url: str = "redis://localhost:6379/0"
    conversation_ttl: int = 604800  # 7 dias
    history_max_messages: int = 20

    # OpenAI / GPT-5-mini
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_temperature: float | None = None
    openai_max_output_tokens: int = 600
    # gpt-5 são modelos de raciocínio: 'minimal'|'low'|'medium'|'high'.
    # 'low' deixa tokens de saída sobrando p/ a resposta (evita conteúdo vazio).
    openai_reasoning_effort: str = "low"

    # Evolution API (WhatsApp)
    evolution_base_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = "vega"

    # Supabase (registros + dashboard de vendas)
    supabase_url: str = ""          # ex.: https://xxxx.supabase.co
    supabase_service_key: str = ""  # service_role (fica só no backend)

    # OmniVoice (STT/TTS)
    omnivoice_base_url: str = ""
    omnivoice_api_key: str = ""
    omnivoice_tts_voice: str = "vega-pt-br"
    omnivoice_stt_language: str = "pt"
    voice_reply_enabled: bool = True
    voice_reply_max_chars: int = 400

    @field_validator("openai_temperature", mode="before")
    @classmethod
    def _blank_temperature_is_none(cls, v: object) -> object:
        """OPENAI_TEMPERATURE vazio no .env -> usa o default do modelo (None)."""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v

    @property
    def system_prompt(self) -> str:
        """Lê o system prompt da Vega do arquivo de texto."""
        return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
