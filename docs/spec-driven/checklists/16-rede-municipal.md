# Fase 16 — Rede municipal de saúde

> SPEC: RF08, ADR-15 · Origem: o usuário observou (2026-10-27) que uma UBS de bairro raramente tem chat próprio; o atendimento digital do SUS vem de plataformas municipais. Decisões dele: assistente da **Secretaria Municipal de Saúde**, cidade **sem nome**, só as unidades com nomes fictícios.

## T-30 — Assistente da Secretaria Municipal de Saúde para toda a rede
**ACs:** AC-RF08-1..4 · **Depende de:** T-29

### Especificação (SPEC primeiro)
- [x] §1.1 (módulo de plataforma de saúde digital do SUS municipal), RF08 com regras e AC-RF08-1..4, §5.5 (documentos da rede), ADR-15, datasets (§7.3), matriz (§7.4) e T-30 no plano

### Conteúdo
- [x] `unidades.md` (novo): resumo de horários num único trecho e uma seção por unidade — UBS Jardim Esperança (única aberta no sábado), UBS Vila Nova (sem dentista e sem farmácia), UBS Santa Clara (horário estendido até 21h e especialidades por encaminhamento), Farmácia Municipal, CAPS e UPA 24h
- [x] `funcionamento.md`: UBS de referência e como descobri-la (Central de Atendimento ou UBS mais próxima com comprovante), senhas, documentos, cadastro, farmácias e privacidade
- [x] `vacinas.md`, `exames.md` e `especialidades.md` reescritos para a rede (seções e preparos mantidos)

### Código
- [x] `prompts.py`: assistente da Secretaria Municipal de Saúde em todos os prompts e textos fixos; **regra da pergunta ambígua** na geração (listar as unidades ou perguntar, nunca escolher); agendamento e encaminhamento remetem à **UBS de referência**, sem pedir endereço; encaminhamento das especialidades para a UBS Santa Clara
- [x] `jevs/choice.json`, `jevs/noul.json`, `jevs/score.json`, descrições das ferramentas em `tools.py`, título da API e docstrings do `rag.py`
- [x] Frontend: cabeçalho "Saúde Digital · Assistente virtual" e "Secretaria Municipal de Saúde · demonstração com unidades fictícias", texto de boas-vindas, sugestão "Qual UBS abre no sábado?", título e descrição da página
- [x] Contrato das ferramentas, rotas e nomes internos (`ubs_docs`) sem mudança

### Testes (335 → 340 passed)
- [x] `test_rede_municipal.py` (4): documentos fictícios e sem nome de cidade, com as três UBS (AC-RF08-1); resumo de horários num único trecho; regra da pergunta ambígua no prompt (AC-RF08-3); respostas com "UBS de referência" e sem pedir endereço (AC-RF08-4)
- [x] `dataset_rede.jsonl` (9 casos: 7 informativas, 1 ambígua, 1 sem documento → fallback) e validação em `test_eval_dataset.py`
- [x] `dataset.jsonl`: notas dos casos rag-02, 03, 04, 11 e 12 atualizadas para os fatos da rede (rotas e expectativas mantidas)
- [x] `test_graph_tools.py`: texto da especialidade indisponível

### Verificação
- [x] Suíte completa: **340 passed**; typecheck do frontend sem erros
- [x] Rodar `run_eval.py` com o Llama real nos 50 casos e no `dataset_rede.jsonl`, com revisão manual — **feito na T-31 (2026-10-27)**, ver [17-avaliacao-rede.md](17-avaliacao-rede.md). **AC-RF08-3 falhou:** nas 2 perguntas ambíguas (rede-amb-01 e rag-02) o modelo escolheu a UBS Santa Clara; a regra no prompt não basta para o Llama 3B
- [ ] Nova captura de tela (`docs/screenshot.png`) com o cabeçalho novo — **pendente com o usuário** (sem ferramenta de navegador nesta sessão)
