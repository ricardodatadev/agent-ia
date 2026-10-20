# Fase 5 — Observabilidade e resiliência

> SPEC: RNF01, RNF02, RNF04, RNF05, RNF06

## T-10 — Logs, métricas por nó, timeouts e erros
**ACs:** RNF05, RNF06 · **Depende de:** T-08, T-09

### Logs estruturados
- [ ] Logger JSON configurado em `main.py` (`JsonFormatter`, uma linha por evento)
- [ ] `request_id` (uuid4) gerado por requisição e retornado na resposta
- [ ] Um log por requisição (`chat_request`) com: `request_id`, `route`, `guardrail`, `score`, `fallback`, `tool`, `llm_calls`, `timings_ms` por nó, `total_ms`, `message_len`, `history_len`
- [ ] Nunca logar texto de mensagens (reconfirmado AC-RF02-5; `guardrail_block` também em JSON)

### Métricas por nó
- [ ] Medir latência de cada nó em `timings_ms`
- [ ] Incrementar `llm_calls` a cada chamada ao LLM
- [ ] Conferir limites (testado por rota): RAG = 4; agendamento = 3; fora do nicho = 2; urgência = 1; bloqueio por regex = 0

### Resiliência
- [ ] Timeout por chamada ao LLM (30 s → **120 s** após medição em CPU, ADR-10) (`client_kwargs={"timeout": LLM_TIMEOUT_S}`) e no cliente Qdrant
- [ ] LLM ou Qdrant indisponível → `503` com `{"detail": "Serviço temporariamente indisponível. Tente novamente em instantes."}`
- [ ] Sem stack trace na resposta HTTP (apenas no log, evento `dependency_error`)
- [ ] Sem retry/circuit breaker além dos retries únicos das decisões (anti-overengineering)

### Health check
- [ ] `GET /health` real: verifica Qdrant (`count`), Ollama (`/api/tags`) e `collection_points`
- [ ] Retorna `503` se algum componente estiver indisponível

### Verificação
- [ ] Com Ollama parado, `/chat` retorna `503` amigável (testado com fakes **e** com os clientes reais, sem Docker)
- [ ] Com Qdrant parado, `/health` retorna `503` (idem)
- [ ] Bloqueio por regex: latência no backend < 50 ms (RNF02) — medido ~8 ms
- [ ] **Extra:** bloqueio por regex continua funcionando mesmo com o LLM fora do ar

> Observação: com Qdrant/Ollama desligados no Windows, `/health` leva ~8 s (recusa de conexão lenta no SO). Com os serviços no ar, a resposta é imediata.
