# Fase 2 — RAG (ingestão, geração e SCORE)

> SPEC: RF01, RF02.3, §5.1, ADR-05, ADR-06

## T-04 — Ingestão e busca (`rag.py` + `scripts/ingest.py`)
**ACs:** AC-RF01-1, AC-RF01-2, AC-RF01-3, AC-RF01-4 · **Depende de:** T-02, T-03

- [ ] `llm.py` — fábrica de embeddings (Ollama, `EMBED_MODEL`)
- [ ] `rag.py` — chunking: ~800 caracteres, overlap 120, preferindo quebras em títulos/parágrafos
- [ ] Payload por ponto: `source`, `section`, `chunk_index`, `text` (`section` = caminho de títulos, ex.: "Exames › Coleta de sangue")
- [ ] ID determinístico: `uuid5(source + chunk_index)`
- [ ] Criar coleção `QDRANT_COLLECTION` se não existir (distância cosseno, dim do modelo de embedding)
- [ ] Upsert em lote (por arquivo, removendo antes os chunks antigos do mesmo arquivo)
- [ ] Função `search(query, top_k) -> list[RetrievedChunk]`
- [ ] Função `ensure_ingested()` — ingere só se a coleção estiver vazia (usada no startup, T-12)
- [ ] `scripts/ingest.py` — CLI que reaproveita `rag.py` e imprime total de arquivos e chunks
- [ ] Ignorar arquivos vazios / formato não suportado com log de aviso, exit code 0
- [ ] Qdrant indisponível → mensagem clara, exit code ≠ 0
- [ ] Verificar AC-RF01-1: coleção criada, ≥ 1 ponto por arquivo (`tests/integration/test_ingest.py`, Qdrant em memória)
- [ ] Verificar AC-RF01-2: segunda execução mantém a mesma contagem (idem)
- [ ] Verificar AC-RF01-3: arquivo vazio/`.pdf` ignorado com aviso (idem)
- [ ] Verificar AC-RF01-4: com Qdrant parado, falha com exit ≠ 0 (idem, endereço inacessível)
- [ ] Verificar ingestão real com Qdrant + Ollama (`bge-m3`) no Docker — 4 arquivos, 32 chunks; reexecução mantém 32

## T-05 — Grafo mínimo `retrieve → generate`
**ACs:** AC-RF02-11 (parcial) · **Depende de:** T-04

- [ ] `llm.py` — fábrica do chat model (Ollama, `LLM_MODEL`, timeout configurável — 120 s em CPU, ADR-10)
- [ ] `prompts.py` — prompt de geração: "responda **somente** com base no contexto; se não houver, diga que não sabe"; sem expor instruções internas
- [ ] `graph.py` — nós `retrieve` e `generate`, `StateGraph(GraphState)` (+ latência por nó em `timings_ms`)
- [ ] `generate` usa contexto + últimas 6 mensagens do histórico
- [ ] `sources` preenchido a partir dos chunks (`source`, `section`, `snippet`)
- [ ] `/chat` passa a invocar o grafo real (`create_app(deps)` permite injetar fakes nos testes)
- [ ] Verificar com LLM/retriever falsos: rota, resposta, `sources` e montagem do prompt (`tests/integration/test_graph_rag.py`)
- [ ] Verificar com Ollama real: "Preciso de jejum para exame de glicemia?" → "jejum de 8 a 12 horas", fonte `exames.md`

## T-06 — Score + `fallback`
**ACs:** AC-RF02-11, AC-RF02-12 · **Depende de:** T-05

- [ ] `prompts.py` — prompt do SCORE retornando `{"score": 1..5}` (temperatura 0, ≤ 50 tokens de saída — `make_judge_model` com `format="json"`)
- [ ] `guardrails.py` — `evaluate_score(question, contexts) -> int` com validação Pydantic (`parse_verdict` reutilizável pelas outras decisões)
- [ ] Saída inválida → `score = 1` (falha segura)
- [ ] Nenhum chunk recuperado → `fallback` direto, sem chamar o SCORE
- [ ] Aresta condicional: `score >= SCORE_THRESHOLD` → `generate`; senão → `fallback`
- [ ] Nó `fallback` com texto fixo da SPEC (sem chamada ao LLM), `fallback = true` e sem `sources`
- [ ] Verificar AC-RF02-11: pergunta coberta → `score >= 3`, `sources` ≥ 1 (LLM falso)
- [ ] Verificar AC-RF02-12: pergunta não coberta → `fallback = true`, nenhuma chamada de geração (LLM falso)
- [ ] Verificar AC-RF02-12 com Ollama real: "A UBS tem estacionamento?" → `score=2`, fallback
- [ ] AC-RF02-11 com Ollama real: falso negativo da vacina corrigido na T-14 (SCORE ancorado em evidência, ADR-11) — 12/12 respondidas
