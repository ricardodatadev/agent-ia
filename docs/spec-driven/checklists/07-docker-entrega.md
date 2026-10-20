# Fase 7 — Docker e execução unificada

> SPEC: RF05, ADR-09, ADR-10

## T-12 — Dockerfiles, compose completo e ingestão automática
**ACs:** AC-RF05-1, AC-RF05-2 · **Depende de:** T-04, T-11

### Backend
- [x] `backend/Dockerfile` (Python 3.12 slim, `requirements.txt` instalado em camada própria, usuário não-root)
- [x] **Extra:** `requirements-dev.txt` separado (pytest fora da imagem) e `.dockerignore`
- [x] Startup chama `rag.ensure_ingested()` — ingere só se a coleção estiver vazia (falha vai para o log, não derruba a API)
- [x] Porta 8000

### Frontend
- [x] `frontend/Dockerfile` (multi-stage: build com Node 22 → nginx servindo na porta 5173)
- [x] `VITE_API_URL` apontando para o backend (build arg, URL vista pelo navegador)

### Compose
- [x] Serviços `backend` e `frontend` adicionados ao `docker-compose.yml`
- [x] `backend` com `depends_on`: `qdrant` saudável e `ollama-pull` concluído com sucesso
- [x] `backend` lê `.env` (URLs internas sobrescritas para `ollama`/`qdrant`); healthcheck via `/health`
- [x] `CORS_ORIGINS` inclui `http://localhost:5173`
- [x] Ingestão manual disponível: `docker compose run --rm backend python scripts/ingest.py`
- [x] **Extra:** `.gitattributes` com `eol=lf` para arquivos usados nos containers

### Ajustes após medição real (CPU, sem GPU)
- [x] `llama3.2:3b` como padrão desde o início (ADR-09) — com 3B + `bge-m3` carregados, o Ollama usa ~4 GB dos ~7,2 GB da VM
- [x] `LLM_TIMEOUT_S=120`, `TOP_K=3`, `OLLAMA_KEEP_ALIVE=-1` (ADR-10) já aplicados desde a T-01/T-02
- [x] Timeout do frontend 300 s (desde a T-11)
- [x] **Achado e correção — aquecimento no startup (RF05 na SPEC):** sem ele, as 2 primeiras perguntas após `docker compose up` deram **503** (Llama carregando a frio ~95 s > timeout de 120 s). Só carregar o modelo ainda deixava a 1ª pergunta RAG em **216 s** (bge-m3 frio + ~30 s por prompt de sistema na 1ª avaliação). O backend agora gera 1 token, 1 embedding e roda uma vez Noul/Choice/Score antes de aceitar requisições (~140 s na 1ª subida, `start_period` 300 s): 1ª pergunta RAG em **98 s**, Noul/Choice em 3–4 s

### Verificação (real, no Docker)
- [x] AC-RF05-1: `docker compose up` → frontend em `http://localhost:5173` (200) e `GET /health` = `200` (`collection_points: 32`) — com a coleção apagada antes, o startup ingeriu sozinho: `startup_ingest_done` 4 arquivos / 32 chunks; backend como `appuser` (não-root)
- [x] AC-RF05-2: reiniciar (`down` + `up`) não baixa modelos ("já disponível") nem refaz a ingestão (`startup_ingest_skipped`)
- [x] Ingestão manual idempotente: 4 arquivos, 32 chunks, contagem inalterada
- [x] Fluxo ponta a ponta com Llama real (12 perguntas): RAG, agendamento (com/sem especialidade, indisponível), urgência, atendente, fora do nicho, PII regex, PII semântica, ofensa — **sem 503**: 12/12 com o aquecimento (antes dele: 10/12, dois 503 no modelo frio)
- [x] Fluxo ponta a ponta **na UI** com Llama real (Edge headless contra a stack do compose): RAG com 3 fontes e relevância 5/5, urgência com prioridade e 192 (4 s), CPF com selo LGPD (0,1 s) — `docs/screenshot.png`

### Latência observada (CPU, `llama3.2:3b`, modelo já carregado)
| Rota | Tempo típico (reconstrução, 20/10) |
| :--- | :--- |
| Bloqueio por regex | ~0 s (9 ms no backend) |
| Bloqueio Noul-LLM / urgência | 3–4 s |
| Agendamento / atendente | 9–33 s |
| RAG com fallback | ~30 s |
| RAG com geração | 70–75 s |
| 1ª pergunta RAG após subir | 98 s com aquecimento (216 s sem; 503 sem nenhum) |
