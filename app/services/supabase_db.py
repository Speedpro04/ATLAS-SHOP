"""Cliente do Supabase (PostgREST) — registros da Vega + dados do dashboard.

Tudo via service_role (fica só no backend). É best-effort: se o Supabase
estiver fora, a Vega continua respondendo (só não grava o registro).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger("vega.supabase")

_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _rest(path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


# ----------------------------- ESCRITA -----------------------------

def upsert_lead(phone: str, nome: str | None = None, marina_nome: str | None = None) -> str | None:
    """Garante o lead pelo telefone e retorna o id. Atualiza nome/marina se vierem."""
    if not enabled():
        return None
    now = datetime.now(timezone.utc).isoformat()
    row = {"telefone": phone, "ultima_mensagem_em": now}
    if nome:
        row["nome"] = nome
    if marina_nome:
        row["marina_nome"] = marina_nome
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(
                _rest("vega_leads"),
                params={"on_conflict": "telefone"},
                headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
                json=row,
            )
            r.raise_for_status()
            data = r.json()
            return data[0]["id"] if data else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        logger.exception("Falha ao upsert do lead %s", phone)
        return None


def log_message(phone: str, papel: str, conteudo: str, canal: str = "texto",
                lead_id: str | None = None) -> None:
    """Registra uma mensagem (best-effort). O contador total_mensagens e a
    ultima_mensagem_em do lead são atualizados por trigger no banco."""
    if not enabled():
        return
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(
                _rest("vega_mensagens"),
                headers=_headers({"Prefer": "return=minimal"}),
                json={"lead_id": lead_id, "telefone": phone, "papel": papel,
                      "conteudo": conteudo, "canal": canal},
            )
            r.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Falha ao registrar mensagem de %s", phone)


# ----------------------------- LEITURA (dashboard) -----------------------------

def _get(path: str, params: dict, count: bool = False) -> tuple[list, int]:
    headers = _headers({"Prefer": "count=exact"} if count else None)
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(_rest(path), params=params, headers=headers)
        r.raise_for_status()
        total = 0
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            try:
                total = int(cr.split("/")[-1])
            except ValueError:
                total = 0
        return r.json(), total


def dashboard_stats() -> dict:
    """Resumo para o dashboard: KPIs, funil e atividade recente."""
    estagios = ["novo", "em_conversa", "qualificado", "agendado", "ganho", "perdido"]
    funil = {e: 0 for e in estagios}
    out = {
        "ok": enabled(),
        "total_leads": 0,
        "funil": funil,
        "ganhos": 0,
        "agendados": 0,
        "qualificados": 0,
        "mensagens_hoje": 0,
        "leads_recentes": [],
        "mensagens_recentes": [],
    }
    if not enabled():
        return out
    try:
        leads, total = _get(
            "vega_leads",
            {"select": "telefone,nome,marina_nome,frota,estagio,total_mensagens,ultima_mensagem_em",
             "order": "ultima_mensagem_em.desc", "limit": "12"},
            count=True,
        )
        out["total_leads"] = total
        out["leads_recentes"] = leads

        # funil completo (só estágio, todos os leads)
        all_estagios, _ = _get("vega_leads", {"select": "estagio", "limit": "10000"})
        for row in all_estagios:
            e = row.get("estagio")
            if e in funil:
                funil[e] += 1
        out["ganhos"] = funil["ganho"]
        out["agendados"] = funil["agendado"]
        out["qualificados"] = funil["qualificado"]

        # mensagens de hoje (UTC)
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
        _, msgs_hoje = _get("vega_mensagens",
                            {"select": "id", "created_at": f"gte.{hoje}", "limit": "1"},
                            count=True)
        out["mensagens_hoje"] = msgs_hoje

        # últimas mensagens
        recentes, _ = _get("vega_mensagens",
                           {"select": "telefone,papel,conteudo,canal,created_at",
                            "order": "created_at.desc", "limit": "15"})
        out["mensagens_recentes"] = recentes
    except (httpx.HTTPError, ValueError):
        logger.exception("Falha ao montar stats do dashboard")
        out["ok"] = False
    return out
