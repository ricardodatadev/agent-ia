# Fase 1 — Fundação

> SPEC: §1.4 (premissas), §5.3 (API), §5.4 (estrutura), §5.5 (documentos), RF05

## T-01 — Esqueleto do backend
**ACs:** AC-RF05-1 (parcial) · **Depende de:** —

- [x] Criar estrutura `backend/app/`, `backend/scripts/`, `backend/data/`, `backend/tests/{unit,integration,eval}/`
- [x] `requirements.txt` com versões fixadas: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `langgraph`, `langchain-ollama`, `qdrant-client`, `httpx` (`pytest` em `requirements-dev.txt`) (+ `langchain-core` e `ollama`, usados diretamente)
- [x] `config.py` — `Settings` (pydantic-settings) lendo: `OLLAMA_BASE_URL`, `LLM_MODEL`, `EMBED_MODEL`, `QDRANT_URL`, `QDRANT_COLLECTION`, `TOP_K=3` (era 4, ADR-10), `SCORE_THRESHOLD=3`, `CORS_ORIGINS` (+ `LLM_TIMEOUT_S`, `AUTO_INGEST`)
- [x] `models.py` — schemas da API e do estado:
  - [x] `ChatTurn` (`role: Literal["user","assistant"]`, `content`)
  - [x] `ChatRequest` (`message` 1–1000 chars, `history` ≤ 6 itens)
  - [x] `ChatResponse` (`request_id`, `reply`, `route`, `guardrail`, `tool_call`, `score`, `fallback`, `sources`)
  - [x] `Route` (`BLOQUEIO | CONSULTA_RAG | AGENDAMENTO | ATENDIMENTO_HUMANO | FORA_DO_NICHO`)
  - [x] `GuardrailResult`, `ToolCallInfo`, `RetrievedChunk`, `Source`
  - [x] `GraphState` (TypedDict, SPEC §5.2)
- [x] `main.py` — FastAPI com CORS restrito a `CORS_ORIGINS`
  - [x] `POST /chat` stub retornando `ChatResponse` fixo e válido
  - [x] `GET /health` stub
- [x] Verificar: `uvicorn app.main:app` sobe e `/docs` mostra os contratos (verificado via `TestClient`: `/openapi.json` expõe `ChatRequest`/`ChatResponse`; CORS testado com origem permitida e negada)
- [x] Verificar: request com `message` vazia ou > 1000 chars retorna `422` (também `422` para histórico > 6)

## T-02 — Infra base no Docker Compose
**ACs:** AC-RF05-2 · **Depende de:** T-01

- [ ] `docker-compose.yml` com serviço `qdrant` (porta 6333, volume nomeado, healthcheck)
- [ ] Serviço `ollama` (porta 11434, volume nomeado para modelos, healthcheck)
- [ ] Pull idempotente de `llama3.2:3b` (antes `llama3.1:8b`, ver ADR-09) e `bge-m3` (serviço `ollama-pull`: só baixa se `ollama show` falhar)
- [ ] `.env.example` com todas as variáveis de `config.py`
- [ ] `.env` no `.gitignore`
- [ ] `docker compose config` válido
- [ ] Verificar: `docker compose up qdrant ollama` sobe saudável (verificado em 19/10, junto da T-12)
- [ ] Verificar: segundo `up` **não** baixa os modelos novamente (AC-RF05-2) — log: "Modelo llama3.2:3b já disponível."

## T-03 — Documentos de exemplo
**ACs:** — · **Depende de:** —

> Conteúdo **fictício**. Nenhum dado real de paciente.

- [ ] `data/funcionamento.md` — horários, endereço e telefone fictícios, documentos necessários para consulta
- [ ] `data/vacinas.md` — calendário de vacinação, campanhas (ex.: influenza)
- [ ] `data/exames.md` — exames disponíveis e preparo (jejum, coleta de urina etc.)
- [ ] `data/especialidades.md` — especialidades (mesma lista de `tools.py`) e fluxo de encaminhamento
- [ ] Usar títulos Markdown (`#`, `##`) — alimentam o campo `section` do payload
- [ ] Anotar 2–3 perguntas **não cobertas** pelos documentos para usar em AC-RF02-12:
  - "A UBS tem estacionamento?"
  - "A UBS aceita plano de saúde particular?"
  - "Qual o nome do diretor da UBS?"
