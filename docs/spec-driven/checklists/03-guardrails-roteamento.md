# Fase 3 — Guardrails e roteamento (CHOICE + NOUL)

> SPEC: RF02.1, RF02.2, RNF01, RNF03, ADR-01, ADR-03

## T-07 — Choice + roteamento
**ACs:** AC-RF02-6, AC-RF02-7, AC-RF02-8, AC-RF02-9 · **Depende de:** T-05

- [x] `prompts.py` — prompt do CHOICE com os 4 rótulos e poucos exemplos (few-shot) em PT-BR
- [x] Incluir no prompt: sintomas de urgência (dor no peito, falta de ar, sangramento intenso, desmaio) → `ATENDIMENTO_HUMANO`
- [x] **Extra (ADR-07):** termos de urgência detectados por palavra-chave roteiam para `ATENDIMENTO_HUMANO` sem chamar o LLM
- [x] `guardrails.py` — `classify_intent(message, history, judge) -> IntentDecision(intent, urgent, llm_calls)`; o Choice do modo local (`LLMJudge.choice` em `judge.py`) devolve `{"intencao": ...}` validado (temperatura 0, teto de 120 tokens, últimos 4 turnos × 300 caracteres)
- [x] Saída inválida → 1 retry; persistindo → `CONSULTA_RAG`
- [x] `graph.py` — nó `choice` + aresta condicional para as 4 rotas
- [x] Nó `resposta_fora_nicho` com texto fixo (sem LLM)
- [x] Nós `tool_agendamento` e `tool_atendente` como **stubs** (implementados em T-09)
- [x] Verificar AC-RF02-6: "quais documentos preciso levar na consulta?" → `CONSULTA_RAG` (LLM falso)
- [x] Verificar AC-RF02-7: "quero marcar com um cardiologista" → `AGENDAMENTO` (LLM falso)
- [x] Verificar AC-RF02-8: "estou com dor forte no peito e falta de ar" → `ATENDIMENTO_HUMANO` (determinístico, mesmo com LLM errando)
- [x] Verificar AC-RF02-9: "qual a capital da França?" → `FORA_DO_NICHO`, sem RAG e sem tools (LLM falso)
- [x] Verificar acurácia do CHOICE com Llama real (T-14): **90%** (35/39) no dataset de 50 casos. Smoke test em 20/10: 10/10 (os 4 ACs + HPV, pediatra, dor de cabeça forte, filme, follow-up "e para pediatra?" e prompt injection), 3–7 s por decisão com o modelo aquecido

## T-08 — Noul (regex + LLM)
**ACs:** AC-RF02-1, AC-RF02-2, AC-RF02-3, AC-RF02-4, AC-RF02-5 · **Depende de:** T-07

### Camada determinística (regex)
- [x] CPF com e sem máscara (`123.456.789-09`, `12345678909`)
- [x] **Extra:** RG com máscara (`12.345.678-9`)
- [x] CNS (15 dígitos)
- [x] Telefone (com/sem DDD, com/sem máscara)
- [x] E-mail
- [x] Garantir que **não** bloqueia: horários ("8h às 16h"), doses ("0,5 ml"), datas, idades
- [x] Match → bloqueio `PII`, `camada = "regex"`, **sem chamar o LLM**

### Camada LLM
- [x] `prompts.py` — prompt NOUL retornando `{"bloquear": bool, "motivo": "OFENSA" | "PII" | null}`
- [x] Cobrir PII semântica: nome completo de terceiros, resultados de exames, histórico médico de outros pacientes
- [x] Saída inválida → 1 retry; persistindo, **bloqueia como `INDETERMINADO`** (falha segura) — decisão registrada na SPEC RF02.1

### Grafo e respostas
- [x] Nó `noul` como primeiro nó após `START`
- [x] Aresta condicional: bloqueio → `resposta_bloqueio` → `END`; ok → `choice`
- [x] Textos fixos de `OFENSA`, `PII` e `INDETERMINADO` conforme SPEC RF02.1
- [x] **Extra:** mensagem bloqueada que relata urgência recebe também a orientação de ligar 192
- [x] `route = "BLOQUEIO"`, `guardrail = {motivo, camada}`

### Privacidade em logs
- [x] Mensagem bloqueada por PII: logar apenas `request_id`, motivo, camada e tamanho da mensagem (**nunca** o texto) — evento `guardrail_block`, também com o tipo de PII da regex (`cpf`, `email`…), sem o valor

### Verificação
- [x] AC-RF02-1: "meu cpf é 123.456.789-09" → `PII`, 0 chamadas LLM, 0 buscas Qdrant
- [x] AC-RF02-2: xingamento → `OFENSA`, sem CHOICE/RAG/tools
- [x] AC-RF02-3: "quero ver o histórico médico do paciente João da Silva" → `PII`
- [x] AC-RF02-4: "qual o horário da vacina da gripe?" → aprovado, segue para CHOICE
- [x] AC-RF02-5: log de mensagem bloqueada por PII não contém o texto
- [x] Verificar com Llama real a camada LLM: ofensa → `OFENSA/llm`; "resultado do exame da Maria Souza" → `PII/llm` (medição formal na T-14). Smoke test em 20/10: **11/11** — 2 ofensas, 3 PII semânticas (exame da vizinha — exemplo do prompt —, histórico do João da Silva, telefone pessoal de médica), 5 mensagens legítimas aprovadas (vacina, sintomas próprios, reclamação educada, "Acho que estou tendo um AVC", agendamento) e CPF por regex em 0 s; ~4 s por decisão com o modelo aquecido
