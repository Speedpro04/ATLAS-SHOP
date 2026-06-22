# 🛥️ Vega — Vendedora Digital Yachts Atlas

Vendedora digital por WhatsApp (texto + voz) para o **Programa Marinas Fundadoras**.
Persona **Vega**, método **SPIN Selling**, cérebro **GPT-5-mini**.

- **FastAPI** — recebe o webhook da Evolution e responde na hora (200), enfileirando o trabalho.
- **Celery + Redis** — processam a mensagem em background (transcreve → pensa → fala → envia).
- **Redis** — também guarda a memória da conversa por lead.
- **Evolution API** — canal WhatsApp (recebe/envia texto e áudio).
- **OmniVoice** — STT (ouvir o lead) e TTS (voz da Vega).

Conhecimento e regras da persona: [VEGA-SYSTEM-PROMPT.md](VEGA-SYSTEM-PROMPT.md) ·
base completa: [VENDEDOR-DIGITAL-ATLAS-SHOP.md](VENDEDOR-DIGITAL-ATLAS-SHOP.md).

---

## Arquitetura (fluxo de uma mensagem)

```
WhatsApp ──▶ Evolution API ──webhook──▶ FastAPI (/webhook/evolution)
                                           │  responde 200 na hora
                                           ▼
                                     Celery (Redis broker)
                                           │
              ┌────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
       OmniVoice STT              GPT-5-mini (Vega +              OmniVoice TTS
     (se veio áudio)             histórico do Redis)           (resposta curta)
                                           │
                                           ▼
                              Evolution API (envia texto
                                  e/ou áudio de volta)
```

Regra de mídia: **texto sempre**; **áudio** só em respostas curtas sem preço/link/@.

---

## Estrutura

```
app/
  main.py            FastAPI + webhook
  config.py          Settings (lê do .env)
  celery_app.py      Instância do Celery
  tasks.py           process_message (orquestra tudo)
  memory.py          Histórico + perfil por lead (Redis)
  schemas.py         Parsing do payload da Evolution
  services/
    llm.py           GPT-5-mini (OpenAI)
    evolution.py     Enviar texto/áudio, baixar mídia
    voice.py         OmniVoice STT/TTS
prompts/
  vega_system_prompt.txt   System prompt da Vega
```

---

## Como rodar

### Opção A — Docker (recomendado)

```bash
cp .env.example .env      # preencha as chaves
docker compose up --build
```

Sobe `redis`, `api` (porta 8000) e `worker`.

### Opção B — Local (dev)

Precisa de um Redis rodando (`redis://localhost:6379/0`).

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # preencha as chaves

# Terminal 1 — API
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Worker do Celery
celery -A app.celery_app.celery_app worker --loglevel=info --queues=vega
```

Verifique: `GET http://localhost:8000/health` deve retornar `{"status":"ok","redis":true}`.

---

## Configurar o webhook na Evolution API

Aponte a instância para a API da Vega (com o token):

```
URL do webhook:  https://SEU-HOST/webhook/evolution?token=SEU_WEBHOOK_TOKEN
Eventos:         MESSAGES_UPSERT
Base64 de mídia: ATIVADO  (para a Vega receber o áudio do lead direto)
```

Variáveis em `.env` (veja `.env.example` para a lista completa): `OPENAI_API_KEY`,
`EVOLUTION_BASE_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `OMNIVOICE_*`,
`WEBHOOK_TOKEN`, `REDIS_URL`.

> ⚠️ **OmniVoice:** os endpoints em `app/services/voice.py` são uma suposição razoável
> (`/v1/transcriptions` e `/v1/speech`). Ajuste caminho/headers conforme a doc da sua conta.
> Sem OmniVoice configurado, a Vega funciona **só em texto** (degrada com segurança).

---

## Teste rápido sem WhatsApp

Simule um evento da Evolution direto no webhook:

```bash
curl -X POST "http://localhost:8000/webhook/evolution?token=SEU_WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "instance": "vega",
    "data": {
      "key": {"remoteJid": "5512999999999@s.whatsapp.net", "fromMe": false, "id": "ABC"},
      "pushName": "Marina Teste",
      "message": {"conversation": "Oi, vi a página das marinas fundadoras"}
    }
  }'
```

A resposta da Vega chega no WhatsApp do número (precisa da Evolution conectada).

---

## Guard rails

As regras invioláveis da Vega (não certifica pela Marinha, não promete retorno,
não cita outras marinas, sempre agenda os 15 min) vivem no system prompt em
`prompts/vega_system_prompt.txt`. Edite lá para ajustar o comportamento — não
precisa mexer no código.

*Um produto Axos Hub.*
