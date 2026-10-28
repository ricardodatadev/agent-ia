# Fase 13 — Tokens por decisão

> SPEC: RNF06 · Origem: dúvida do usuário (2026-10-23) sobre comparar o gasto de tokens das decisões feitas pelo LLM e pelo Jev.

## T-27 — Registro de tokens no LLMJudge e soma no `run_eval.py`
**ACs:** RNF06 · **Depende de:** T-26

> **Lacuna encontrada:** o `JevJudge` já registrava os tokens (`jev_answer`), mas o `LLMJudge` devolvia só o texto e descartava o `usage_metadata` do modelo — não havia como comparar os dois motores.

### Especificação (SPEC primeiro)
- [x] RNF06: evento por decisão (`llm_answer` no modo local, `jev_answer` no Jev) com decisão, modelo e tokens de entrada e saída — nunca o texto; verificação pelo `run_eval.py`

### Código
- [x] `judge.py`: `LLMJudge._ask(decision, system, user)` lê `usage_metadata` da resposta e registra `llm_answer` (`decision`, `llm_model`, `input_tokens`, `output_tokens`); modelo sem contagem → `None`, sem quebrar
- [x] `run_eval.py`: `TokenCollector` (handler de log) soma os tokens por decisão em cada caso — vale para `llm_answer` e `jev_answer`; novas métricas: tokens por decisão (média por chamada), por mensagem (média) e total; o JSON dos resultados traz `decision_tokens` por caso e o `engine` (`llm` ou `jev`)

### Testes (312 → 319 passed)
- [x] `test_llm_tokens.py` (7): tokens e rótulo de cada decisão (`noul`, `choice`, `score`); um evento por tentativa; modelo sem contagem; **LGPD: nem a mensagem nem o prompt vão para o log**; coletor soma por decisão e ignora outros eventos; métricas somam por decisão, por mensagem e no total; sem dados, não aparecem linhas de tokens

### Verificação
- [x] Suíte completa: **319 passed**
- [x] Ollama real (`llama3.2:3b`): o `usage_metadata` vem preenchido — Noul: **481 e 486 tokens de entrada, 14 e 16 de saída** por decisão (a maior parte da entrada é o prompt de sistema com exemplos)
- [x] Rodar `run_eval.py` completo com o Llama e registrar a tabela de tokens por decisão: 1126 de entrada e 35 de saída por mensagem, em média — **feito na T-31 (2026-10-27)**, ver [17-avaliacao-rede.md](17-avaliacao-rede.md)
- [ ] Rodar o mesmo dataset com o Jev e comparar acertos, tokens, chamadas, tempo e custo — **pendente: requer `TYPESAFE_API_KEY`**
