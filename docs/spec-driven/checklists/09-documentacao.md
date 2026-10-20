# Fase 9 — Documentação

> SPEC: §1, §5, §8, §9, RNF07

## T-15 — README
**ACs:** — · **Depende de:** T-12, T-14

### Conteúdo
- [ ] Visão geral do projeto e aviso de que é demonstração (dados fictícios, não substitui atendimento médico)
- [ ] **Extra:** screenshot de conversa real (`docs/screenshot.png`) e diagrama Mermaid do grafo
- [ ] Diagrama do grafo (SPEC §5.1) e explicação das 3 decisões (Noul, Choice, Score)
- [ ] Como a arquitetura economiza tokens (bloqueio por regex, respostas fixas, early exit)
- [ ] Decisões arquiteturais e trade-offs (resumo dos ADRs da SPEC §9)
- [ ] Pré-requisitos (Docker, RAM/GPU recomendada)
- [ ] Como rodar: `cp .env.example .env && docker compose up --build`
- [ ] Como reingerir documentos manualmente
- [ ] Como rodar testes e a avaliação
- [ ] Resultados da avaliação (tabela gerada em T-14)
- [ ] Como trocar de nicho: substituir `data/`, prompts em `prompts.py`, textos padrão e tools
- [ ] Limitações conhecidas e próximos passos

### Fechamento da v1
- [ ] Questões em aberto da SPEC §10 resolvidas ou registradas como próximos passos
- [ ] Premissas `[PREMISSA]` da SPEC revisadas
- [ ] SPEC com status atualizado para `v1 concluída`
- [ ] Todas as fases marcadas no [índice](00-indice.md)
