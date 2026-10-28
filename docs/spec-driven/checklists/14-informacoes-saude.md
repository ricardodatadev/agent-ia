# Fase 14 — Informações gerais de saúde

> SPEC: RF07 · Origem: pedido do usuário (2026-10-27) de ampliar o assistente para dúvidas gerais de saúde com dados oficiais, sem ampliar a arquitetura.

## T-28 — Resumos do Ministério da Saúde no RAG, sem diagnóstico nem remédio
**ACs:** AC-RF07-1..6 · **Depende de:** T-27

> **Decisão de escopo:** não há API pública do Ministério que responda perguntas de saúde (as APIs abertas do DATASUS são estatísticas). O conteúdo informativo está nas páginas *Saúde de A a Z*, que entram no RAG como documentos. O conteúdo do gov.br está sob CC BY-ND 3.0, então os arquivos são **resumos redigidos pelo projeto** com os fatos das páginas, sem copiar trechos e com a fonte no topo.

### Especificação (SPEC primeiro)
- [x] RF07 com regras e AC-RF07-1..6; objetivo (§1.1), documentos (§5.5), datasets complementares (§7.3), matriz (§7.4), risco "modelo fecha diagnóstico" (§8) e T-28 no plano de tarefas

### Conteúdo
- [x] `backend/data/saude-dengue.md`, `saude-gripe.md`, `saude-hipertensao.md`, `saude-diabetes.md`: fonte (gov.br/saude) e aviso no topo; títulos com o nome da doença (ajudam a busca e a checagem de assunto do Score); sem nomes de medicamentos ou doses

### Código
- [x] `prompts.py`: geração explica informação geral, mas nunca diz se o paciente tem uma doença nem indica remédio; Choice manda pergunta geral sobre doença para `CONSULTA_RAG` e relato de sintoma, pedido de diagnóstico ou de remédio para `ATENDIMENTO_HUMANO` (com exemplos); Noul não bloqueia pergunta geral sobre doença; Score e resposta de fora do nicho citam as informações de saúde
- [x] `prompts.py`: `HEALTH_INFO_NOTICE` e `with_health_notice` — aviso fixo quando algum trecho usado na geração é de `saude-*.md`; `graph.py` aplica no nó `generate`
- [x] `jevs/choice.json` e `jevs/score.json`: mesmas definições para o Jev
- [x] `rag.py`: `expected_chunks` e `ensure_ingested` completam a coleção quando faltam pontos (volume antigo recebe os documentos novos na subida, sem comando manual)
- [x] Frontend: sugestão "Quais são os sintomas da dengue?" no lugar de "Quais documentos levo na consulta?"

### Testes (319 → 330 passed)
- [x] `test_health_info.py` (9): os 4 documentos existem; cada um cita a fonte oficial, traz o aviso e não cita medicamento (AC-RF07-1); aviso só com trecho de saúde (AC-RF07-5); grafo com modelos simulados: resposta de saúde termina com o aviso (AC-RF07-2), resposta só com documento da UBS e fallback não recebem (AC-RF07-5)
- [x] `test_ingest.py`: coleção com parte dos arquivos é completada na subida e não reingere quando completa (AC-RF07-6)
- [x] `dataset_saude.jsonl` (14 casos: 7 informativas, 3 pedidos de diagnóstico, 2 de remédio, 2 doenças sem documento → fallback) e `test_eval_dataset.py`: formato válido e nenhum caso decidido pela camada determinística

### Verificação
- [x] Suíte completa: **330 passed**; typecheck do frontend sem erros
- [x] Coleção passa de 32 para **62 pontos** (os 4 documentos novos geram 30 chunks)
- [x] Rodar `run_eval.py --dataset tests/eval/dataset_saude.jsonl` com o Llama real (AC-RF07-2..4): 14/14 sem divergências, 7 respostas revisadas à mão sem diagnóstico nem remédio — **feito na T-31 (2026-10-27)**, ver [17-avaliacao-rede.md](17-avaliacao-rede.md)
- [x] Rodar o `dataset.jsonl` original de novo: Choice 38/39, RAG coberto 10/12 (rag-01 encaminhado à equipe, rag-07 com nota 2) — **feito na T-31 (2026-10-27)**, ver [17-avaliacao-rede.md](17-avaliacao-rede.md)
