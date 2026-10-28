# Fase 17 — Avaliação com o Llama real depois da rede municipal

> SPEC: §7.3 · Rodada de 2026-10-27, `llama3.2:3b` em CPU, decisões no modo local, `top_k=3`. Resultados brutos em `backend/tests/eval/results/` (ignorado pelo git).

## T-31 — Rodada nos 4 datasets
**Depende de:** T-30

### Execução
- [x] Stack reconstruída (`docker compose up -d --build`) e documentos reingeridos à mão (9 arquivos, 71 trechos)
- [x] `dataset_rede.jsonl` (9), `dataset_saude.jsonl` (14), `dataset_robustez.jsonl` (16) e `dataset.jsonl` (50)

### Resultados
| Dataset | Choice | RAG coberto | Fallback correto | Urgência | Noul | Tool |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `dataset.jsonl` (50) | 38/39 (97%) | 10/12 | 4/4 | 7/7 | 11/11, 0 falsos positivos | 17/17 |
| `dataset_saude.jsonl` (14) | 14/14 | 7/7 | 2/2 | — | 0 falsos positivos | 5/5 |
| `dataset_robustez.jsonl` (16) | 9/11 | 2/2 | — | 7/7 | 5/5 | 7/8 |
| `dataset_rede.jsonl` (9) | 8/9 | 6/8 | 0/1 (resposta segura, ver abaixo) | — | 0 falsos positivos | — |

### Divergências e revisão manual
- [x] **Pergunta ambígua (AC-RF08-3) falhou 2/2:** "Até que horas o posto fica aberto?" e "Que horas a UBS abre?" foram respondidas só com a UBS Santa Clara (7h às 21h); a segunda ainda disse "não abre aos sábados", o que é falso para a UBS Jardim Esperança. A regra no prompt não segura o Llama 3B
- [x] "Qual UBS abre no sábado?" escolheu a unidade certa, mas disse que ela abre "apenas aos sábados"
- [x] Erros seguros: rag-07 e rede-inf-02 caíram no fallback com nota 2; rag-01 (jejum) e rede-inf-06 (CAPS) foram para a equipe; rede-nao-01 (telefone da UPA) respondeu que não encontrou, sem inventar número (conta como divergência porque não passou pelo fallback fixo)
- [x] Robustez: rob-neg-03 ("meu pai teve infarto há 10 anos") e rob-neg-04 ("o que é um AVC?") viraram urgência, as limitações já documentadas da regra de termos
- [x] Fidelidade (revisão manual): saúde 7/7 fiéis, com o aviso fixo e sem diagnóstico nem remédio; dataset principal 8/11 (rag-02 da pergunta ambígua, rag-06 com redação confusa e rag-12 com uma frase não suportada)
- [x] Custo: 1126 tokens de entrada e 35 de saída por mensagem nas decisões, em média; resposta RAG completa em ~82 s na CPU

### Próximo passo proposto
- [x] Tirar a pergunta ambígua do LLM, como já é feito com a urgência: pergunta de horário sem unidade citada → resumo de horários da rede como texto fixo — **feito na T-32**, ver [18-pergunta-ambigua.md](18-pergunta-ambigua.md)
