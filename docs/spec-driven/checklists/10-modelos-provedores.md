# Fase 10 — Pós-v1: modelo Qwen e provedores configuráveis

> SPEC: P01, ADR-06, ADR-12, ADR-13 · Solicitação: trocar o LLM padrão para Qwen e permitir Claude/Gemini via `.env`

## T-16 — Provedor do LLM configurável (Ollama / Claude / Gemini)
**ACs:** troca de provedor apenas pelo `.env`; padrão continua local · **Depende de:** v1

- [x] `config.py` — `LLM_PROVIDER` (`ollama` | `anthropic` | `google`), `ANTHROPIC_API_KEY`, `ANTHROPIC_EFFORT`, `GOOGLE_API_KEY` (chaves como `SecretStr`)
- [x] `llm.py` — fábrica por provedor:
  - [x] Ollama: igual à v1 (JSON + temperatura 0 nas decisões)
  - [x] Claude: sem `temperature` (rejeitada pelos modelos atuais), `effort` configurável via `output_config`, `max_tokens` com folga para o thinking
  - [x] Gemini: `response_mime_type="application/json"` nas decisões
  - [x] Chave ausente → erro claro citando a variável
- [x] Respostas lidas com `.text` (APIs devolvem blocos de thinking junto do texto)
- [x] Falhas de rede, rate limit e 5xx das APIs → `503`; chave inválida → `500` com log (erro de configuração)
- [x] Embeddings e Qdrant sempre locais (Ollama), qualquer que seja o provedor
- [x] `ollama-pull` baixa o LLM só com `LLM_PROVIDER=ollama` (desde a T-02); com API, o aquecimento do startup carrega só o `bge-m3` e não gasta tokens aquecendo as decisões
- [x] `.env.example` com blocos comentados: Llama 3B (padrão), Llama 8B, Qwen 3B/1.5B, Claude, Gemini — com aviso de LGPD (arquivo do projeto reaproveitado)
- [x] Testes unitários sem rede (`tests/unit/test_llm.py`): seleção de provedor, payload do Claude, JSON do Gemini, erro sem chave, mapeamento de erros (+ 500/503 na API em `test_api.py`) — **199 passed**
- [x] **Extra:** fail-fast verificado no container: `LLM_PROVIDER=anthropic` sem chave → `LLMConfigError: LLM_PROVIDER=anthropic exige ANTHROPIC_API_KEY no .env`; padrão Ollama reconstruído e verificado (agendamento e bloqueio)
- [ ] Verificação real com Claude/Gemini — **não executada: sem chaves de API neste ambiente** (comportamento coberto por testes de construção/payload)

## T-17 — Trocar o LLM padrão para `qwen2.5:3b`
**ACs:** metas da SPEC mantidas (AC-RF02-10..13, AC-RF03) · **Depende de:** T-16

> **Reconstrução (20/10):** por decisão do usuário, a comparação Llama × Qwen **não foi refeita** — a decisão já documentada no ADR-12 foi reaproveitada (Llama 3.2 3B como padrão; Qwen como opção no `.env`). Os números abaixo são os da construção anterior, registrados na SPEC.

- [x] Decisão do ADR-12 reaproveitada: `llama3.2:3b` continua o padrão (`config.py`, `.env.example`); `qwen2.5:3b` e `qwen2.5:1.5b` como opções comentadas no `.env.example`
- [x] Comparação de referência (construção anterior, 50 casos, CPU): CHOICE 100% (Llama 97%) · **urgência 86% (Llama 100%) — abaixo da meta AC-RF02-10** · NOUL falsos positivos 5% (Llama 0%) · RAG coberto 92% (Llama 100%) · tool 94% (Llama 100%) · RAG médio 69 s (Llama 49 s)
- [x] Decisão e viés registrados na SPEC (ADR-12)
- [x] README: modelo padrão, tabela de opções de provedor e modelo (seção "Modelos e provedores") e aviso de LGPD para provedores externos

## T-18 — Ajustes para portfólio (pós-comparação)
**ACs:** padrão atinge todas as metas da SPEC; CI verde · **Depende de:** T-17

- [x] `llama3.2:3b` como padrão (na reconstrução, nunca deixou de ser — T-17); Qwen 3B/1.5B como opções comentadas no `.env.example`
- [x] README e SPEC atualizados (tabela de opções na seção "Modelos e provedores", ADR-12 com decisão e viés)
- [x] CI no GitHub Actions (`.github/workflows/ci.yml`): pytest (Python 3.12) + typecheck/build do frontend (Node 22), com cache de pip/npm e cancelamento de execuções antigas; selo no README
- [x] CI simulado localmente em containers limpos (`python:3.12-slim` e `node:22-alpine`, a partir de `git archive HEAD` — sem `.venv`/`.env`): **199 passed** em 15 s e build ok
- [x] `docs/especificacao_de_requisitos.md` com o nome correto (na reconstrução já veio assim; link da SPEC ok)
- [x] Screenshot do README com `llama3.2:3b` (gerado na T-12, Edge headless contra a stack real)
- [x] **Achado:** com `OLLAMA_KEEP_ALIVE=-1`, trocar de modelo mantém o anterior em memória (5,7 GB de 7,2 GB com Llama + Qwen + bge-m3, medido na construção anterior) e as respostas estouram o timeout → documentado no README, seção "Problemas comuns" (`docker compose restart ollama`)
- [ ] GIF/vídeo curto da demo no topo do README — **com o usuário**
- [ ] Repositório público, descrição e tópicos no GitHub — **com o usuário**
- [ ] Confirmar o primeiro run do CI verde no GitHub após o push — **com o usuário**

## T-19 — Modo demonstração configurável na interface
**ACs:** linha "Rota · relevância" só aparece com `SHOW_DEBUG=true`; fontes e selos sempre visíveis · **Depende de:** T-11

- [ ] `Badges.tsx`: linha de rota/nota condicionada a `VITE_SHOW_DEBUG === "true"` (ausente = desligado)
- [ ] `frontend/Dockerfile`: build arg `VITE_SHOW_DEBUG` (padrão `false`)
- [ ] `docker-compose.yml`: `VITE_SHOW_DEBUG: ${SHOW_DEBUG:-true}` (demo de portfólio ligada por padrão)
- [ ] `.env.example`: `SHOW_DEBUG=true` com instrução de rebuild; README com a explicação
- [ ] Verificado com Edge headless contra a stack real: `SHOW_DEBUG=false` → selo de guardrail visível e **sem** "Rota:"; padrão → "Rota:" visível

## T-20 — README reescrito para portfólio
- [ ] Removidos: coluna "Quando usar", resultados da avaliação, comparação de modelos, falhas do Qwen e tabela de latência
- [ ] Nova seção sobre as decisões Noul, Choice e Score: pontos de controle, camadas determinísticas, falha segura e economia de tokens por encerramento antecipado (tabela de chamadas por tipo de mensagem, com a ressalva de que no RAG completo as decisões acrescentam chamadas). Será revista na T-25 para o Jev da TypeSafe AI
- [ ] Nova seção "Por que guardrails importam": urgência, LGPD, alucinação, uso fora do propósito e tools — risco × guardrail × funcionamento
- [ ] Números de avaliação e comparação continuam registrados na SPEC (ADR-11, ADR-12) e no checklist 08
