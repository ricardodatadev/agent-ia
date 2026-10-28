# Fase 18 — Pergunta de horário sem unidade decidida no código

> SPEC: RF08 (regra 3), AC-RF08-3, AC-RF08-5 · Origem: na avaliação da T-31, o Llama 3B ignorou a regra do prompt e escolheu uma unidade nas 2 perguntas ambíguas ("que horas a UBS abre?" respondeu só a UBS Santa Clara e disse "não abre aos sábados").

## T-32 — Resumo de horários da rede como resposta fixa
**ACs:** AC-RF08-3, AC-RF08-5 · **Depende de:** T-31

### Especificação (SPEC primeiro)
- [x] RF08 regra 3 com a decisão no código, AC-RF08-3 revisado, AC-RF08-5 novo, T-32 no plano e matriz

### Código
- [x] `guardrails.py`: `asks_network_hours` — termo de horário + unidade genérica ("UBS", "posto", "unidade"), sem unidade, serviço ou exame citado na mensagem nem nas últimas 4 mensagens do cidadão; "funciona" fica de fora ("como funciona o cadastro?")
- [x] `rag.py`: `hours_summary` lê o trecho "Resumo de horários das unidades" de `unidades.md` (o documento continua sendo a fonte; nada duplicado no código)
- [x] `prompts.py`: `network_hours_reply` (introdução fixa + resumo + convite a dizer qual é a UBS)
- [x] `graph.py`: nó `resposta_horarios` depois do Choice, só na rota `CONSULTA_RAG`; `unidades.md` nas fontes; sem retrieve, Score nem geração. `main.py` carrega o resumo no startup; sem o documento, o grafo segue o RAG de sempre

### Testes (340 → 358 passed)
- [x] `test_graph_horarios.py` (18): 5 perguntas ambíguas detectadas; 7 com unidade, serviço ou sem horário que seguem o RAG (AC-RF08-5); unidade dita antes na conversa; resumo lido do documento; grafo com 2 chamadas ao LLM e fonte `unidades.md` (AC-RF08-3); sem resumo carregado e em outra rota, nada muda
- [x] `test_stack_real.py`: número de arquivos ingeridos lido de `data/` (o teste ainda esperava os 4 documentos de antes da T-28); 8 passed contra a stack real

### Verificação com o Llama real
- [x] `dataset_rede.jsonl`: 7/9 corretas (antes 6/9); rede-amb-01, rede-inf-01 e rede-inf-02 respondidas com o resumo em 8–12 s, com 2 chamadas ao LLM. Restam rede-inf-06 (CAPS encaminhado à equipe) e rede-nao-01 (telefone da UPA: respondeu que não encontrou, sem inventar)
- [x] `dataset.jsonl`, casos de horário: rag-02 com o resumo; rag-03, rag-04 e rag-11 continuam pelo RAG, corretos (sem regressão)
- [x] Backend do Docker reconstruído com a mudança
