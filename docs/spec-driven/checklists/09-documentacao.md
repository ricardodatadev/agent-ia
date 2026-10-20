# Fase 9 — Documentação

> SPEC: §1, §5, §8, §9, RNF07

## T-15 — README
**ACs:** — · **Depende de:** T-12, T-14

### Conteúdo
- [x] Visão geral do projeto e aviso de que é demonstração (dados fictícios, não substitui atendimento médico)
- [x] **Extra:** screenshot de conversa real (`docs/screenshot.png`, gerado na T-12 com o Llama) e diagrama Mermaid do grafo
- [x] Diagrama do grafo (SPEC §5.1) e explicação das 3 decisões (Noul, Choice, Score)
- [x] Como a arquitetura economiza tokens (bloqueio por regex, respostas fixas, early exit)
- [x] Decisões arquiteturais e trade-offs (resumo dos ADRs da SPEC §9)
- [x] Pré-requisitos (Docker, RAM/GPU recomendada)
- [x] Como rodar: `cp .env.example .env && docker compose up --build`
- [x] Como reingerir documentos manualmente
- [x] Como rodar testes e a avaliação
- [x] Resultados da avaliação (tabela da T-14), com o que a avaliação mudou no sistema
- [x] Como trocar de nicho: substituir `data/`, prompts em `prompts.py`, textos padrão e tools
- [x] Limitações conhecidas e próximos passos

### Fechamento da v1
- [x] Questões em aberto da SPEC §10 resolvidas ou registradas como próximos passos
- [x] Premissas `[PREMISSA]` da SPEC revisadas
- [x] SPEC com status atualizado para `v1 concluída`
- [x] Todas as fases da v1 marcadas no [índice](00-indice.md)
