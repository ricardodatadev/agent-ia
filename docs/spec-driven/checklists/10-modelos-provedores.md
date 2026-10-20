# Fase 10 — Pós-v1: modelo Qwen e provedores configuráveis

> SPEC: P01, ADR-06, ADR-12, ADR-13 · Solicitação: trocar o LLM padrão para Qwen e permitir Claude/Gemini via `.env`

## T-16 — Provedor do LLM configurável (Ollama / Claude / Gemini)
**ACs:** troca de provedor apenas pelo `.env`; padrão continua local · **Depende de:** v1

- [ ] `config.py` — `LLM_PROVIDER` (`ollama` | `anthropic` | `google`), `ANTHROPIC_API_KEY`, `ANTHROPIC_EFFORT`, `GOOGLE_API_KEY` (chaves como `SecretStr`)
- [ ] `llm.py` — fábrica por provedor:
  - [ ] Ollama: igual à v1 (JSON + temperatura 0 nas decisões)
  - [ ] Claude: sem `temperature` (rejeitada pelos modelos atuais), `effort` configurável via `output_config`, `max_tokens` com folga para o thinking
  - [ ] Gemini: `response_mime_type="application/json"` nas decisões
  - [ ] Chave ausente → erro claro citando a variável
- [ ] Respostas lidas com `.text` (APIs devolvem blocos de thinking junto do texto)
- [ ] Falhas de rede, rate limit e 5xx das APIs → `503`; chave inválida → `500` com log (erro de configuração)
- [ ] Embeddings e Qdrant sempre locais (Ollama), qualquer que seja o provedor
- [ ] `ollama-pull` baixa o LLM só com `LLM_PROVIDER=ollama`
- [ ] `.env.example` com blocos comentados: Qwen 3B (padrão), Qwen 1.5B, Llama 3B/8B, Claude, Gemini — com aviso de LGPD
- [ ] Testes unitários sem rede (`tests/unit/test_llm.py`): seleção de provedor, payload do Claude, JSON do Gemini, erro sem chave, mapeamento de erros
- [ ] Verificação real com Claude/Gemini — **não executada: sem chaves de API neste ambiente** (comportamento coberto por testes de construção/payload)

## T-17 — Trocar o LLM padrão para `qwen2.5:3b`
**ACs:** metas da SPEC mantidas (AC-RF02-10..13, AC-RF03) · **Depende de:** T-16

- [ ] `LLM_MODEL=qwen2.5:3b` como padrão (`config.py`, `.env.example`)
- [ ] Baixar o modelo e subir a stack (`qwen2.5:3b`, 1,9 GB; `/health` ok)
- [ ] Avaliação completa (50 casos) com `qwen2.5:3b` e comparação com `llama3.2:3b`:
  - CHOICE 100% (Llama 97%) · **urgência 86% (Llama 100%) — abaixo da meta AC-RF02-10**
  - NOUL falsos positivos 5% (Llama 0%) · RAG coberto 92% (Llama 100%) · tool 94% (Llama 100%) · RAG médio 69 s (Llama 49 s)
- [ ] Registrar resultado e decisão (ADR-12) na SPEC — Qwen mantido como padrão por decisão do usuário; desvio documentado; precedência da urgência sobre o NOUL-LLM proposta e não adotada
- [ ] Atualizar README (modelo padrão, comparação de modelos, tabela de opções de provedor, aviso de LGPD, limitação de urgência com o Qwen)

## T-18 — Ajustes para portfólio (pós-comparação)
**ACs:** padrão atinge todas as metas da SPEC; CI verde · **Depende de:** T-17

- [ ] Padrão volta para `llama3.2:3b` (ADR-12 revisado); Qwen 3B/1.5B como opções comentadas no `.env.example`
- [ ] README e SPEC atualizados (tabela de opções, comparação com o Llama como padrão, decisão e viés da avaliação)
- [ ] CI no GitHub Actions (`.github/workflows/ci.yml`): pytest (Python 3.12) + typecheck/build do frontend (Node 22); selo no README
- [ ] CI simulado localmente em containers limpos (`python:3.12-slim` e `node:22-alpine`, sem `.venv`/`.env`): **167 passed** e build ok
- [ ] `docs/especifica_o_de_requisitos.md` → `docs/especificacao_de_requisitos.md` (`git mv`; link na SPEC atualizado)
- [ ] Screenshot do README refeito com `llama3.2:3b`
- [ ] **Achado:** com `OLLAMA_KEEP_ALIVE=-1`, trocar de modelo mantém o anterior em memória (5,7 GB de 7,2 GB com Llama + Qwen + bge-m3) e as respostas estouram o timeout → documentado no README (`docker compose restart ollama`)
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
