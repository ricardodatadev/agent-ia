# Fase 8 — Testes e avaliação

> SPEC: §7, RNF01, RNF08, AC-RF02-10, AC-RF02-13

## T-13 — Testes unitários e de integração
**ACs:** todos os automatizáveis · **Depende de:** T-08, T-09

### Unitários (`tests/unit/`, sem Ollama/Qdrant)
- [ ] `test_pii_regex.py` — CPF (com/sem máscara), CNS, telefone, e-mail
- [ ] `test_pii_regex.py` — falsos positivos: horários, doses, datas, idades **não** bloqueiam
- [ ] `test_jev_parsing.py` — NOUL, CHOICE, SCORE: JSON válido, inválido, fora do domínio
- [ ] `test_jev_parsing.py` / `test_routing.py` — CHOICE inválido → retry → `CONSULTA_RAG`; SCORE inválido → `1`; NOUL inválido → retry → `INDETERMINADO`
- [ ] `test_routing.py` — classificação/urgência; arestas condicionais cobertas no grafo completo (`test_graph_*.py`)
- [ ] `test_tools.py` — args válidos, especialidade ausente/inválida, formato do protocolo
- [ ] `test_chunking.py` — tamanho/overlap, IDs determinísticos

### Integração (`tests/integration/`)
- [ ] Fixtures de **LLM falso** (respostas roteirizadas) e **retriever falso**
- [ ] `test_graph_bloqueio.py` — regex: 0 chamadas LLM; NOUL-LLM: sem CHOICE/RAG
- [ ] `test_graph_rag.py` — `score >= 3` → generate; `< 3` → fallback sem geração
- [ ] `test_graph_tools.py` — agendamento e atendente, incluindo "192" na urgência
- [ ] `test_graph_rotas.py` + `test_api.py` — rotas e `llm_calls` por rota dentro dos limites (RNF01)
- [ ] `test_api.py` (`TestClient`) — contrato de `/chat`, `422`, `503` com dependência simulada indisponível
- [ ] `test_ingest.py` — Qdrant em memória (sempre roda); `test_stack_real.py` — `@pytest.mark.integration`, Qdrant real: idempotência (AC-RF01-2)
- [ ] **Extra:** `test_stack_real.py` — regressão de recuperação com `bge-m3` real (top-1 de 5 perguntas) e separação de similaridade fora do nicho

### Verificação
- [ ] `pytest` (padrão exclui `integration`) passando sem Docker — **147 passed**
- [ ] `pytest -m integration` passando com a stack do compose em execução — **7 passed**

## T-14 — Dataset e runner de avaliação
**ACs:** AC-RF02-10, AC-RF02-13 · **Depende de:** T-13

### Dataset (`tests/eval/dataset.jsonl`, 50 exemplos)
- [ ] CONSULTA_RAG coberta — 12
- [ ] CONSULTA_RAG não coberta — 4
- [ ] AGENDAMENTO — 7 (incluindo sem especialidade e especialidade indisponível)
- [ ] ATENDIMENTO_HUMANO / urgência — 7 urgentes (1 **sem** palavra-chave) + 3 não urgentes (incluindo reclamação educada)
- [ ] FORA_DO_NICHO — 6 (incluindo prompt injection)
- [ ] OFENSA — 4
- [ ] PII (regex e semântica) — 7 (3 regex + 4 LLM, incluindo dado de funcionária e saúde de terceiro)
- [ ] Cada linha: `{"id", "message", "expected_route", "expected_guardrail", "expected_fallback", "expected_tool", "urgent", "notes"}`

### Runner (`tests/eval/run_eval.py`, Ollama real)
- [ ] Executa o grafo para cada exemplo e salva resultados em JSON (`tests/eval/results/`, ignorado pelo git)
- [ ] Métricas: acurácia por decisão (Noul, Choice, Score), recall de urgência, taxa de fallback, latência média por nó, média de `llm_calls` por rota
- [ ] Gera tabela Markdown para colar no README (+ lista de divergências); `--only` e `--label` para rodadas parciais

### Achados do smoke test real (19/10) — tratados
- [ ] SCORE com falso negativo ("vacina da gripe" com nota 2) → **corrigido** com SCORE ancorado em evidência (ADR-11)
- [ ] CHOICE: "Qual a capital da França?" → `CONSULTA_RAG` — **mantido como limitação conhecida**: 1 erro em 39, falha segura
      (SCORE = 1 → fallback). Adicionar exemplo de geografia ao prompt seria ajustar ao próprio teste
- [ ] Opções avaliadas: variante B (escala direta) → falso positivo (wi-fi nota 5), descartada; variante C (evidência) + conferência
      determinística da citação → adotada; pré-filtro por similaridade e `llama3.2:1b` → **não necessários** (metas atingidas)
- [ ] Latência: RAG 57 s → 49 s em média (SCORE 27 s → 19 s); aquecimento no startup fica como próximo passo (README)

### Resultados — antes × depois (`llama3.2:3b`, CPU, top_k=3)
| Métrica | Linha de base | Final (evidência, overlap 0,7) | Meta |
| :--- | :--- | :--- | :--- |
| CHOICE: acurácia | 38/39 (97%) | 38/39 (97%) | ≥ 85% ✅ |
| Recall de urgência | 7/7 (100%) | 7/7 (100%) | 100% ✅ |
| NOUL: bloqueios / motivo correto | 11/11 / 11/11 | 11/11 / 11/11 | ✅ |
| NOUL: falsos positivos | 0/39 | 0/39 | ✅ |
| RAG coberto respondido | 11/12 (92%) | **12/12 (100%)** | AC-RF02-11 ✅ |
| RAG não coberto → fallback | 4/4 | 4/4 | AC-RF02-12 ✅ |
| Tool correta | 17/17 | 17/17 | AC-RF03 ✅ |
| Tempo médio RAG | 57,5 s | 49,3 s | — |

> Rodadas: `baseline` (50), `evidencia` (50, overlap 0,8 — expôs acentos corrompidos em `rag-11`) e `evidencia-0.7` (22: RAG + fora do nicho, únicas rotas afetadas pelo SCORE).

### Critérios
- [ ] AC-RF02-10: acurácia do CHOICE ≥ 85% — **97%**
- [ ] AC-RF02-10: recall de urgência = 100% — **100%** (inclusive caso sem palavra-chave)
- [ ] AC-RF02-13: revisar respostas geradas — 12/12 fiéis ao contexto (omissões pontuais, nenhuma informação inventada)
- [ ] Se algum critério falhar: ajustar prompts/few-shot, reexecutar e registrar antes/depois — feito para AC-RF02-11 (ADR-11)
