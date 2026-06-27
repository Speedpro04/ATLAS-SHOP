# 🚀 Deploy da Solara no EasyPanel (via GitHub)

A Solara roda como **2 serviços** que compartilham a mesma imagem (mesmo repositório):
**`api`** (FastAPI + dashboard) e **`worker`** (Celery). Os dois usam o **Redis que já existe**
no EasyPanel (`mesaquevps_redis-para-sistemas`).

> ⚠️ Os dois serviços precisam estar no **mesmo projeto/rede** do Redis pra resolver o host
> `mesaquevps_redis-para-sistemas`. Se o Redis estiver em outro projeto, crie a Solara nesse
> mesmo projeto (ou exponha o Redis).

---

## 1. Subir o código no GitHub
Já feito pelo assistente: repositório **privado** no GitHub da conta conectada.
A cada `git push`, o EasyPanel reconstrói automaticamente (se o auto-deploy estiver ligado).

## 2. Criar o serviço da API
No EasyPanel → projeto → **+ Service** → **App**:
- **Source:** GitHub → selecione o repositório → branch `main`
- **Build:** Dockerfile (raiz do repo)
- **Port:** `8000`
- **Domains:** adicione um domínio (ex.: `atlasshop.yachtsatlas.online`) → é por aqui que você abre o **dashboard**
- **Environment** (cole as variáveis — pegue os valores do seu `.env` / `credenciais-vega.txt`):
  ```
  APP_ENV=production
  WEBHOOK_TOKEN=vega-axos-2026
  REDIS_URL=redis://default:SENHA@mesaquevps_redis-para-sistemas:6379/0
  OPENAI_API_KEY=...
  OPENAI_MODEL=gpt-5-mini
  OPENAI_MAX_OUTPUT_TOKENS=1800
  SUPABASE_URL=https://owzelkiyorumnlaycral.supabase.co
  SUPABASE_SERVICE_KEY=sb_secret_...
  EVOLUTION_BASE_URL=https://evoapi.axoshub.com
  EVOLUTION_API_KEY=...
  EVOLUTION_INSTANCE=Ativo_Hub
  VOICE_REPLY_ENABLED=false
  ```
- **Deploy** → aguarde o build. Teste: `https://SEU-DOMINIO/health` deve dar `{"status":"ok","redis":true}`.

## 3. Criar o serviço do Worker
**+ Service** → **App** → mesmo repositório e branch:
- **Build:** Dockerfile
- **Sem domínio** (não recebe HTTP)
- **Environment:** as MESMAS variáveis da API
- **Start / Deploy command** (sobrescreve o CMD do Dockerfile):
  ```
  celery -A app.celery_app.celery_app worker --loglevel=info --queues=solara --concurrency=4
  ```
- **Deploy.**

## 4. Apontar o webhook da Evolution
Na Evolution (instância `Ativo_Hub`), configure o webhook para:
```
https://atlasshop.yachtsatlas.online/webhook/evolution?token=vega-axos-2026
Eventos: MESSAGES_UPSERT   ·   Base64 de mídia: ATIVADO
```

Se você ativar webhook por evento na Evolution, a aplicação também aceita
`/webhook/evolution/messages-upsert`.

## 5. Pronto
- Dashboard: `https://atlasshop.yachtsatlas.online/`
- A Solara já grava leads/mensagens no Supabase e o painel atualiza sozinho.
- Conecte o WhatsApp da instância `Ativo_Hub` (parear QR) pra ela responder de verdade.

---

### Observações
- **Não** suba um Redis novo — use o `mesaquevps_redis-para-sistemas` existente.
- O `.env` **não vai** pro GitHub (está no `.gitignore`); as variáveis vivem no painel do EasyPanel.
- Logo do dashboard: coloque o arquivo em `app/static/logo.png` e dê `git push` (entra na imagem).
