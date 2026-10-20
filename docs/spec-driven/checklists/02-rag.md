# Fase 2 — RAG (ingestão, geração e SCORE)

> SPEC: RF01, RF02.3, §5.1, ADR-05, ADR-06

## T-04 — Ingestão e busca (`rag.py` + `scripts/ingest.py`)
**ACs:** AC-RF01-1, AC-RF01-2, AC-RF01-3, AC-RF01-4 · **Depende de:** T-02, T-03

- [x] `llm.py` — fábrica de embeddings (Ollama, `EMBED_MODEL`)
- [x] `rag.py` — chunking: ~800 caracteres, overlap 120, preferindo quebras em títulos/parágrafos
- [x] Payload por ponto: `source`, `section`, `chunk_index`, `text` (`section` = caminho de títulos, ex.: "Exames › Coleta de sangue")
- [x] ID determinístico: `uuid5(source + chunk_index)`
- [x] Criar coleção `QDRANT_COLLECTION` se não existir (distância cosseno, dim do modelo de embedding)
- [x] Upsert em lote (por arquivo, removendo antes os chunks antigos do mesmo arquivo)
- [x] Função `search(query, top_k) -> list[RetrievedChunk]`
- [x] Função `ensure_ingested()` — ingere só se a coleção estiver vazia (usada no startup, T-12)
- [x] `scripts/ingest.py` — CLI que reaproveita `rag.py` e imprime total de arquivos e chunks
- [x] Ignorar arquivos vazios / formato não suportado com log de aviso, exit code 0
- [x] Qdrant indisponível → mensagem clara, exit code ≠ 0
- [x] Verificar AC-RF01-1: coleção criada, ≥ 1 ponto por arquivo (`tests/integration/test_ingest.py`, Qdrant em memória)
- [x] Verificar AC-RF01-2: segunda execução mantém a mesma contagem (idem)
- [x] Verificar AC-RF01-3: arquivo vazio/`.pdf` ignorado com aviso (idem)
- [x] Verificar AC-RF01-4: com Qdrant parado, falha com exit ≠ 0 (idem, endereço inacessível)
- [x] Verificar ingestão real com Qdrant + Ollama (`bge-m3`) no Docker — 4 arquivos, 32 chunks; reexecução mantém 32 (20/10); busca top-1 correta para glicemia, vacina da gripe, documentos e dentista

## T-05 — Grafo mínimo `retrieve → generate`
**ACs:** AC-RF02-11 (parcial) · **Depende de:** T-04

- [x] `llm.py` — fábrica do chat model (Ollama, `LLM_MODEL`, timeout configurável — 120 s em CPU, ADR-10)
- [x] `prompts.py` — prompt de geração: "responda **somente** com base no contexto; se não houver, diga que não sabe"; sem expor instruções internas
- [x] `graph.py` — nós `retrieve` e `generate`, `StateGraph(GraphState)` (+ latência por nó em `timings_ms`)
- [x] `generate` usa contexto + últimas 6 mensagens do histórico
- [x] `sources` preenchido a partir dos chunks (`source`, `section`, `snippet`)
- [x] `/chat` passa a invocar o grafo real (`create_app(deps)` permite injetar fakes nos testes)
- [x] Verificar com LLM/retriever falsos: rota, resposta, `sources` e montagem do prompt (`tests/integration/test_graph_rag.py`)
- [x] Verificar com Ollama real: "Preciso de jejum para exame de glicemia?" → "jejum de 8 a 12 horas", fonte `exames.md` (51 s); "Qual o horário da vacina da gripe?" → "segunda a sexta, das 8h às 16h, e aos sábados das 8h às 12h", fonte `vacinas.md` (38 s)

## T-06 — Score + `fallback`
**ACs:** AC-RF02-11, AC-RF02-12 · **Depende de:** T-05

- [x] `prompts.py` — prompt do SCORE retornando `{"evidencia": ..., "score": 1..5}` já no formato do ADR-11, com a pergunta após o contexto (temperatura 0, teto de 120 tokens — `make_judge_model` com `format="json"`)
- [x] `judge.py` — `LLMJudge.score(question, contexts) -> (nota, chamadas)` com validação Pydantic (`parse_verdict` reutilizável pelas outras decisões). Implementado direto no módulo da estrutura final (SPEC §5.4), em vez de `guardrails.py`, para não mover código na T-22
- [x] Saída inválida → `score = 1` (falha segura)
- [x] Nenhum chunk recuperado → `fallback` direto, sem chamar o SCORE
- [x] Aresta condicional: `score >= SCORE_THRESHOLD` → `generate`; senão → `fallback`
- [x] Nó `fallback` com texto fixo da SPEC (sem chamada ao LLM), `fallback = true` e sem `sources`
- [x] Verificar AC-RF02-11: pergunta coberta → `score >= 3`, `sources` ≥ 1 (LLM falso)
- [x] Verificar AC-RF02-12: pergunta não coberta → `fallback = true`, nenhuma chamada de geração (LLM falso)
- [x] Verificar AC-RF02-12 com Ollama real: "A UBS tem estacionamento?" → `score=1`, fallback; "Qual o nome do diretor da UBS?" → `score=1`, fallback; "A UBS aceita plano de saúde particular?" → `score=2`, fallback (após a correção abaixo)
- [x] **Achado e correção (revisão do ADR-11):** depois de outras requisições, o Llama deu nota 4 a "plano de saúde particular" citando uma frase **real** de outro assunto (especialidades fora da UBS), o que gerou uma resposta inventada. A conferência passou a exigir também um termo de conteúdo em comum entre a pergunta e a evidência (ou o título da seção dela). Teste de regressão em `test_jev_parsing.py`
- [x] AC-RF02-11 com Ollama real: SCORE já nasce ancorado em evidência (ADR-11) — vacina da gripe, glicemia, documentos e horário da UBS com nota 5 e resposta correta (20/10); medição completa (12 casos) na T-14
