# Checklist — Índice e Progresso

> Derivado de [SPEC.md](../SPEC.md). Em caso de divergência, **a SPEC prevalece** — atualize a SPEC primeiro, depois o checklist.

> **Reconstrução a partir da SPEC iniciada em 2026-10-20** — checklists reiniciados; cada item é marcado quando refeito e verificado nesta reconstrução. **v1 (Fases 1–9) concluída em 2026-10-20.**

## Como usar
- Marque `[x]` apenas quando o item estiver feito **e verificado** (teste passando ou verificação manual registrada).
- Cada tarefa só fecha quando a **Definition of Done** for cumprida:
  - [ ] Código tipado (Pydantic / type hints)
  - [ ] ACs vinculados cobertos por teste ou verificação manual registrada
  - [ ] `pytest` passando
  - [ ] Nenhum segredo no código
  - [ ] SPEC atualizada se o comportamento mudou

## Fases

| Fase | Arquivo | Tarefas | Depende de | Status |
| :--- | :--- | :--- | :--- | :--- |
| 1 | [01-fundacao.md](01-fundacao.md) | T-01, T-02, T-03 | — | ☑ |
| 2 | [02-rag.md](02-rag.md) | T-04, T-05, T-06 | Fase 1 | ☑ |
| 3 | [03-guardrails-roteamento.md](03-guardrails-roteamento.md) | T-07, T-08 | Fase 2 | ☑ |
| 4 | [04-tools.md](04-tools.md) | T-09 | T-07 | ☑ |
| 5 | [05-observabilidade-resiliencia.md](05-observabilidade-resiliencia.md) | T-10 | Fases 3 e 4 | ☑ |
| 6 | [06-frontend.md](06-frontend.md) | T-11 | T-01 (contrato da API) | ☑ |
| 7 | [07-docker-entrega.md](07-docker-entrega.md) | T-12 | T-04, T-11 | ☑ |
| 8 | [08-testes-avaliacao.md](08-testes-avaliacao.md) | T-13, T-14 | Fases 3 e 4 | ☑ |
| 9 | [09-documentacao.md](09-documentacao.md) | T-15 | Fases 7 e 8 | ☑ |
| 10 (pós-v1) | [10-modelos-provedores.md](10-modelos-provedores.md) | T-16 a T-20 | v1 | ◐ T-16 a T-20 feitas; pendentes com o usuário: chamada real a Claude/Gemini (sem chaves), GIF, repositório público e 1º CI verde |
| 11 (pós-v1) | [11-jev-typesafe.md](11-jev-typesafe.md) | T-21 a T-25 | v1 | ◐ T-21 a T-25 feitas; pendentes: chamada real ao Jev e avaliação com o dataset (AC-RF06-7) — requerem `TYPESAFE_API_KEY` |
| 12 (pós-v1) | [12-robustez-decisoes.md](12-robustez-decisoes.md) | T-26 | T-23 | ◐ código e testes feitos (312 passed); pendentes: medição com o LLM real/Jev e CI simulado |
| 13 (pós-v1) | [13-tokens-por-decisao.md](13-tokens-por-decisao.md) | T-27 | T-26 | ◐ registro e soma de tokens feitos (319 passed); pendentes: avaliação completa com o Llama e comparação com o Jev (requer chave) |
| 14 (pós-v1) | [14-informacoes-saude.md](14-informacoes-saude.md) | T-28 | T-27 | ◐ documentos, prompts, aviso fixo e ingestão feitos (330 passed); pendente: avaliação com o Llama real (`dataset_saude.jsonl` e regressão do `dataset.jsonl`) |
| 15 (pós-v1) | [15-respostas-encaminhamento.md](15-respostas-encaminhamento.md) | T-29 | T-28 | ☑ textos e testes feitos (335 passed) |
| 16 (pós-v1) | [16-rede-municipal.md](16-rede-municipal.md) | T-30 | T-29 | ◐ documentos, textos, frontend e testes feitos (340 passed); pendente: avaliação com o Llama real (`dataset_rede.jsonl`) e nova captura de tela |

> A Fase 6 (frontend) pode ser feita em paralelo às Fases 2–5, usando o contrato de `POST /chat` da SPEC §5.3.

## Questões em aberto a resolver (SPEC §10)
- [x] Confirmar modelo LLM (P01) e se a máquina-alvo tem GPU → `llama3.2:3b` em CPU (ADR-09/10)
- [x] Confirmar se o histórico deve sobreviver a recarregamento de página → não (LGPD)
- [x] Fechar lista de especialidades disponíveis → 8, em `tools.py`
- [x] Decidir sobre classificador explícito de prompt injection na v1 → não (SPEC §10)

## Cobertura de critérios de aceite

| RF | ACs | Fase |
| :--- | :--- | :--- |
| RF01 | AC-RF01-1..4 | 2 |
| RF02.1 (NOUL) | AC-RF02-1..5 | 3 |
| RF02.2 (CHOICE) | AC-RF02-6..10 | 3, 8 |
| RF02.3 (SCORE) | AC-RF02-11..13 | 2, 8 |
| RF03 | AC-RF03-1..6 | 4, 15 |
| RF04 | AC-RF04-1..4 | 6 |
| RF05 | AC-RF05-1..2 | 1, 7 |
| RF07 | AC-RF07-1..6 | 14 |
| RF08 | AC-RF08-1..4 | 16 |
| RNF01–RNF08 | — | 5, 8 |
