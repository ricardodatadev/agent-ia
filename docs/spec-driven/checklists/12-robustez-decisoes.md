# Fase 12 — Robustez da urgência e da PII

> SPEC: RF02.1, RF02.2, RF06, ADR-07 (2ª revisão), Apêndices C.1 e C.2 · Origem: dúvida do usuário (2026-10-21) sobre falsos positivos/negativos da regra de urgência.

## T-26 — Urgência pelo Jev com regra como plano B; PII com espaços e por extenso
**ACs:** AC-RF02-14, AC-RF02-15, AC-RF02-16, AC-RF06-5 (revisado), AC-RF06-8, AC-RF06-9 · **Depende de:** T-23

> **Achado que originou a tarefa:** a regra literal tratava como urgência "não estou com dor no peito", "o que é um AVC?" e "meu pai teve infarto há 10 anos" (6/6 falsos positivos testados) e não pegava "dor forte no peito", "aperto no peito", "sem ar", "caiu e não responde". A regra de PII não pegava CPF/telefone com espaços nem e-mail por extenso.
> **Decisão (usuário):** o Jev decide a urgência; a regra de palavras fica como plano B (Jev fora do ar ou sem chave), com trava de negação.

### Especificação (SPEC primeiro)
- [x] RF02.1: PII com espaços/dígito a dígito/"arroba"; bloco de urgência reescrito (Jev → plano B → modo local → trava de negação → limitação conhecida)
- [x] RF02.2, RF05 (`JEV_URGENCY_THRESHOLD`), RF06 (AC-RF06-5 revisado; AC-RF06-8 e AC-RF06-9), ADR-07 (2ª revisão), Apêndices A, C.1 e C.2 (trava de negação com exemplos); documento de requisitos
- [x] Novos ACs: AC-RF02-14 (negação → regra se abstém), AC-RF02-15 (negação que não nega o sintoma → urgência), AC-RF02-16 (PII com espaços/por extenso)

### Código
- [x] `guardrails.py`: `urgency_signal` (`urgent` | `negated` | `none`) com a trava de negação — negador (`nao`, `nunca`, `nem`, `sem`) colado ao termo, com até 4 palavras de ligação; termos que já começam com `nao` nunca são negados
- [x] `guardrails.py`: padrões `numero_longo` (11 dígitos com espaços/pontos/traços) e `email_extenso`
- [x] `judge.py`: `NoulResult(motivo, urgent, calls)`; `Judge.decides_urgency` (Jev `True`, modo local `False`)
- [x] `jevs/noul.json`: pergunta `urgencia` (true: sintomas graves em andamento, mesmo sem termos técnicos; false: perguntas informativas, fatos antigos, sintomas leves ou negados)
- [x] `jev.py`: `urgencia` na mesma requisição do Noul (sem chamada extra); `JEV_URGENCY_THRESHOLD` (0,3); resposta ausente → decide a regra; `config.py` e `.env.example`
- [x] `check_input`: PII por regex → (modo local: regra decide a urgência clara) → Noul → urgência passa à frente dos bloqueios semânticos; **plano B**: se o Jev falhar (conexão, timeout, 429, 5xx, malformada, chave recusada) e a regra reconhecer urgência, o atendimento segue sem o Jev (`urgency_fallback` no log, só metadados); caso contrário o erro original (503/500)
- [x] `classify_intent` recebe a urgência já decidida; `graph.py` guarda `urgent` do Noul no estado

### Testes (284 → 312 passed)
- [x] `test_urgency_guard.py` (26): os 11 casos prototipados + variações; `check_input` com juiz fictício (Jev decide sem consultar a regra; plano B; erro de programação não é engolido)
- [x] `test_jev_judge.py`: urgência pelo Jev sem termo da lista, limiar (0,29 × 0,3), urgência à frente do bloqueio semântico, urgência baixa não consulta a regra, resposta ausente → regra, plano B para conexão/timeout/5xx/chave recusada, 503 sem urgência, LGPD no log do plano B
- [x] `test_pii_regex.py`: variações com espaços/por extenso e falsos positivos (datas, doses, "a arroba do boi")
- [x] `test_jev_questions.py`: pergunta `urgencia` obrigatória no `noul.json`
- [x] `dataset_robustez.jsonl` (16 casos: 7 urgência sem termo/mistas, 4 negação e informativas, 5 PII) + `run_eval.py --dataset`; `test_eval_dataset.py` fixa o que a camada determinística faz com cada caso (inclusive as 2 limitações conhecidas)

### Verificação
- [x] Suíte completa sem Docker: **312 passed**
- [ ] Rodar `run_eval.py --dataset tests/eval/dataset_robustez.jsonl` com o LLM real (modo local) — **pendente: Docker desligado no momento**; comparar com o Jev quando houver `TYPESAFE_API_KEY`
- [ ] Reavaliar o dataset de 50 casos após a mudança (recall de urgência continua 7/7?) — **pendente: mesma razão**
- [ ] CI simulado em `python:3.12-slim` com a mudança — **pendente: Docker desligado**
