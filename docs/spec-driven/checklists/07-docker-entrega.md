# Fase 7 — Docker e execução unificada

> SPEC: RF05, ADR-09, ADR-10

## T-12 — Dockerfiles, compose completo e ingestão automática
**ACs:** AC-RF05-1, AC-RF05-2 · **Depende de:** T-04, T-11

### Backend
- [ ] `backend/Dockerfile` (Python 3.12 slim, `requirements.txt` instalado em camada própria, usuário não-root)
- [ ] **Extra:** `requirements-dev.txt` separado (pytest fora da imagem) e `.dockerignore`
- [ ] Startup chama `rag.ensure_ingested()` — ingere só se a coleção estiver vazia (falha vai para o log, não derruba a API)
- [ ] Porta 8000

### Frontend
- [ ] `frontend/Dockerfile` (multi-stage: build com Node 22 → nginx servindo na porta 5173)
- [ ] `VITE_API_URL` apontando para o backend (build arg, URL vista pelo navegador)

### Compose
- [ ] Serviços `backend` e `frontend` adicionados ao `docker-compose.yml`
- [ ] `backend` com `depends_on`: `qdrant` saudável e `ollama-pull` concluído com sucesso
- [ ] `backend` lê `.env` (URLs internas sobrescritas para `ollama`/`qdrant`); healthcheck via `/health`
- [ ] `CORS_ORIGINS` inclui `http://localhost:5173`
- [ ] Ingestão manual disponível: `docker compose run --rm backend python scripts/ingest.py`
- [ ] **Extra:** `.gitattributes` com `eol=lf` para arquivos usados nos containers

### Ajustes após medição real (CPU, sem GPU)
- [ ] LLM trocado para `llama3.2:3b` (ADR-09) — Ollama usa ~5 GB dos ~7,2 GB da VM com 3B + `bge-m3`
- [ ] `LLM_TIMEOUT_S` 30 → 120, `TOP_K` 4 → 3, `OLLAMA_KEEP_ALIVE=-1` (ADR-10) — eliminou os 503 da rota RAG
- [ ] Timeout do frontend 120 s → 300 s

### Verificação (real, no Docker)
- [ ] AC-RF05-1: `docker compose up` → frontend em `http://localhost:5173` (200) e `GET /health` = `200` (`collection_points: 32`)
- [ ] AC-RF05-2: reiniciar (`down` + `up`) não baixa modelos ("já disponível") nem refaz a ingestão (`startup_ingest_skipped`)
- [ ] Ingestão manual idempotente: 4 arquivos, 32 chunks, contagem inalterada
- [ ] Fluxo ponta a ponta com Llama real (12 perguntas): RAG, agendamento (com/sem especialidade, indisponível), urgência, atendente, fora do nicho, PII regex, PII semântica, ofensa — **sem 503**
- [ ] Fluxo ponta a ponta **na UI** com Llama real — verificado na T-15 (ver 06-frontend.md)

### Latência observada (CPU, `llama3.2:3b`, modelo já carregado)
| Rota | Tempo típico |
| :--- | :--- |
| Bloqueio por regex | ~0 s |
| Bloqueio NOUL-LLM / urgência | 3–4 s |
| Agendamento / atendente | 8–33 s |
| RAG com fallback | ~30 s |
| RAG com geração | ~80 s |
| 1ª requisição após subir (modelo frio) | ~145 s |
