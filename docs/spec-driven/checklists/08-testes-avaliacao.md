# Fase 8 — Testes e avaliação

> SPEC: §7, RNF01, RNF08, AC-RF02-10, AC-RF02-13

## T-13 — Testes unitários e de integração
**ACs:** todos os automatizáveis · **Depende de:** T-08, T-09

### Unitários (`tests/unit/`, sem Ollama/Qdrant)
- [x] `test_pii_regex.py` — CPF (com/sem máscara), CNS, telefone, e-mail
- [x] `test_pii_regex.py` — falsos positivos: horários, doses, datas, idades **não** bloqueiam
- [x] `test_jev_parsing.py` — NOUL, CHOICE, SCORE: JSON válido, inválido, fora do domínio
- [x] `test_jev_parsing.py` / `test_routing.py` — CHOICE inválido → retry → `CONSULTA_RAG`; SCORE inválido → `1`; NOUL inválido → retry → `INDETERMINADO`
- [x] `test_routing.py` — classificação/urgência; arestas condicionais cobertas no grafo completo (`test_graph_*.py`)
- [x] `test_tools.py` — args válidos, especialidade ausente/inválida, formato do protocolo
- [x] `test_chunking.py` — tamanho/overlap, IDs determinísticos

### Integração (`tests/integration/`)
- [x] Fixtures de **LLM falso** (respostas roteirizadas) e **retriever falso**
- [x] `test_graph_bloqueio.py` — regex: 0 chamadas LLM; NOUL-LLM: sem CHOICE/RAG
- [x] `test_graph_rag.py` — `score >= 3` → generate; `< 3` → fallback sem geração
- [x] `test_graph_tools.py` — agendamento e atendente, incluindo "192" na urgência
- [x] `test_graph_rotas.py` + `test_api.py` — rotas e `llm_calls` por rota dentro dos limites (RNF01)
- [x] `test_api.py` (`TestClient`) — contrato de `/chat`, `422`, `503` com dependência simulada indisponível
- [x] `test_ingest.py` — Qdrant em memória (sempre roda); `test_stack_real.py` — `@pytest.mark.integration`, Qdrant real: idempotência (AC-RF01-2)
- [x] **Extra:** `test_stack_real.py` — regressão de recuperação com `bge-m3` real (top-1 de 5 perguntas) e separação de similaridade fora do nicho

### Verificação
- [x] `pytest` (padrão exclui `integration`) passando sem Docker — **170 passed** (20/10, ~30 s)
- [x] `pytest -m integration` passando com a stack do compose em execução — **8 passed** (20/10, ~75 s: inclui reingestão real com bge-m3 numa coleção temporária e checagem da API no ar)

## T-14 — Dataset e runner de avaliação
**ACs:** AC-RF02-10, AC-RF02-13 · **Depende de:** T-13

### Dataset (`tests/eval/dataset.jsonl`, 50 exemplos)
- [x] CONSULTA_RAG coberta — 12
- [x] CONSULTA_RAG não coberta — 4
- [x] AGENDAMENTO — 7 (incluindo sem especialidade e especialidade indisponível)
- [x] ATENDIMENTO_HUMANO / urgência — 7 urgentes (1 **sem** palavra-chave) + 3 não urgentes (incluindo reclamação educada)
- [x] FORA_DO_NICHO — 6 (incluindo prompt injection)
- [x] OFENSA — 4
- [x] PII (regex e semântica) — 7 (3 regex + 4 LLM, incluindo dado de funcionária e saúde de terceiro)
- [x] Cada linha: `{"id", "message", "expected_route", "expected_guardrail", "expected_fallback", "expected_tool", "urgent", "notes"}`

### Runner (`tests/eval/run_eval.py`, Ollama real)
- [x] Executa o grafo para cada exemplo e salva resultados em JSON (`tests/eval/results/`, ignorado pelo git)
- [x] Métricas: acurácia por decisão (Noul, Choice, Score), recall de urgência, taxa de fallback, latência média por nó, média de `llm_calls` por rota
- [x] Gera tabela Markdown para colar no README (+ lista de divergências); `--only` e `--label` para rodadas parciais
- [x] **Extra:** `tests/unit/test_eval_dataset.py` — estrutura e quantidades do dataset e cálculo das métricas, sem LLM

### Achados da avaliação da reconstrução (20/10) — tratados
- [x] **Recall de urgência 5/7 (71%) — abaixo da meta:** o Noul-LLM bloqueou "meu filho … se envenenou" como PII e "estou pensando em me matar" como OFENSA → **urgência passa à frente do Noul-LLM** (só a regex de PII vem antes; ADR-07 revisado na SPEC). Teste de regressão em `test_graph_bloqueio.py`
- [x] **RAG coberto 10/12:** "Que horas a UBS abre?" e "vacina de HPV" com nota 5 e citação correta foram rebaixados pela conferência de assunto criada na T-06 ("horas" × "horário"; citação sem a sigla HPV) → conferência passa a usar o trecho inteiro de onde a citação saiu, radical de 4 letras e siglas de 3 (2ª revisão do ADR-11). O caso do plano de saúde continua barrado. Regressões em `test_jev_parsing.py`
- [x] "Qual o nome do diretor da UBS?" → `FORA_DO_NICHO` e prompt injection → bloqueio `INDETERMINADO`: **mantidos como limitações conhecidas** — falham de forma segura (texto fixo, nada inventado); ajustar o prompt para esses casos seria ajustar ao próprio teste
- [x] Aquecimento no startup feito na T-12 (1ª pergunta RAG 216 s → 98 s)

### Resultados (`llama3.2:3b`, CPU, top_k=3, modo local)
| Métrica | Rodada 1 (`reconstrucao`, 50 casos) | Após as correções | Meta |
| :--- | :--- | :--- | :--- |
| Choice: acurácia | 35/39 (90%) | não remedido (correções não tocam o Choice) | ≥ 85% ✅ |
| Recall de urgência | 5/7 (71%) ❌ | 7/7 esperado: 6 casos por termo de urgência agora deterministicamente à frente do Noul-LLM (testes de regressão) + `urg-07`, que já passava | 100% |
| Noul: bloqueios / motivo correto | 11/11 / 11/11 | inalterado | ✅ |
| Noul: falsos positivos | 3/39 (8%) | 1/39 esperado (sobra o prompt injection, bloqueio seguro) | — |
| RAG coberto respondido | 10/12 (83%) | **12/12** na rodada 2 (interrompida após os 12 casos de RAG: todos com tempo de geração, 60–84 s) | AC-RF02-11 ✅ |
| RAG não coberto → fallback | 3/4 (o 4º caiu em fora do nicho, também sem inventar) | não remedido | AC-RF02-12 |
| Tool correta | 15/17 (88%) | 17/17 esperado (as 2 falhas eram as urgências bloqueadas) | AC-RF03 |
| Tempo médio RAG com geração | 67,9 s | 70,1 s (12 casos da rodada 2) | — |

> A rodada 2 (`reconstrucao-v2`) foi interrompida a pedido após os 12 casos de RAG coberto; os demais números "após as correções" são o efeito esperado das mudanças, garantido por testes de regressão, e não uma nova medição com o LLM.

### Critérios
- [x] AC-RF02-10: acurácia do CHOICE ≥ 85% — **90%** (35/39, rodada 1)
- [x] AC-RF02-10: recall de urgência = 100% — rodada 1: 71%; corrigido com a precedência da urgência sobre o Noul-LLM (6 casos determinísticos + `urg-07` aprovado pelo LLM na rodada 1); não remedido com o LLM
- [x] AC-RF02-13: revisar respostas geradas — revisão manual das 10 respostas geradas na rodada 1: **8/10 fiéis e corretas**; `rag-06` com redação confusa ("lave… mas não o primeiro jato" — o documento diz "despreze o primeiro jato"), sem informação nova; `rag-12` acrescentou uma frase **ausente do contexto** ("é só aguardar o atendimento e agendar a coleta de seus documentos") — alucinação leve, sem risco clínico. Registrado como limitação conhecida do 3B na geração (próximo passo: modelo maior ou verificação da resposta contra o contexto)
- [x] Se algum critério falhar: ajustar e reexecutar registrando antes/depois — feito (urgência e conferência de assunto), sem ajustar prompts ao dataset
