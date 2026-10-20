# Fase 11 — Decisões pelo Jev da TypeSafe AI

> SPEC: RF02, **RF06**, ADR-11, ADR-13, **ADR-14** · Fonte: [docs/especificacao_de_requisitos.md](../../docs/especificacao_de_requisitos.md)
>
> As decisões Noul, Choice e Score passam a ser tomadas pelo **Jev** (modelo de decisões tipadas da TypeSafe AI).
> Sem chave, o **modo local** (LLM configurado) responde às mesmas perguntas. O LLM de geração continua configurável
> (Ollama com Llama ou Qwen, Claude ou Gemini).

## T-21 — Especificação atualizada
**ACs:** — · **Depende de:** v1

> **Reconstrução (20/10):** a SPEC e o documento de requisitos já vieram atualizados; itens conferidos (RF06 e AC-RF06-1..7, ADR-14, glossário, RNF09, AC-RF04-5, Apêndices A–C; requisitos com Jev, RF06, seção 6 e seção 7). Os prompts do Apêndice A foram reescritos nesta reconstrução — por isso a avaliação foi refeita (T-14), como manda a regra 1 do apêndice.

- [x] `docs/especificacao_de_requisitos.md`: Jev como motor das decisões, boas práticas de implementação (seção 6), configuração do `.env` (seção 7) e RF06
- [x] `SPEC.md`: glossário (Jev, Noul, Choice, Score, state do Jev, modo local), RF02 com os dois motores, **RF06** com AC-RF06-1..7, RNF07, estrutura e **ADR-14**
- [x] Termo antigo removido da SPEC, do documento de requisitos e dos checklists
- [x] Correção: RF02.3 passa a citar o limite real de sobreposição da evidência (70%, ADR-11)
- [x] SPEC pronta para reconstrução do zero:
  - [x] RF05 com a lista completa de variáveis do `.env` (LLM, motor de decisões, busca, interface)
  - [x] RF04 com o modo demonstração (`SHOW_DEBUG`) e AC-RF04-5; RNF09 com o CI
  - [x] Matriz de rastreabilidade com o RF06
  - [x] Apêndice A — artefatos de referência (prompts, textos fixos, perguntas do Jev, regex, termos de urgência, especialidades, constantes, documentos, dataset), números de referência e regras para reconstruir
  - [x] Apêndice B — versões fixadas (runtimes, imagens, modelos, pacotes do backend e do frontend, CI)

## T-22 — Interface de decisões e modo local
**ACs:** AC-RF02-1..13 continuam válidos · **Depende de:** T-21

- [x] `judge.py`: `Judge` (Protocol) com `noul`, `choice` e `score`, cada um devolvendo (decisão, nº de chamadas)
- [x] `LLMJudge` (modo local): mesma lógica da v1 (prompts, retries, falha segura, Score ancorado em evidência) — na reconstrução já nasceu em `judge.py` (T-06 a T-08)
- [x] `guardrails.py`: apenas camadas determinísticas (regex de PII, termos de urgência) + orquestração que delega ao juiz
- [x] `graph.py`: `GraphDeps.judge` — o grafo não conhece o provedor
- [x] Comportamento preservado: os 199 testes passaram sem mudar expectativas (+1 teste: `LLMJudge` implementa `Judge`, `runtime_checkable`)

## T-23 — Integração com o Jev via SDK oficial
**ACs:** AC-RF06-3..6 · **Depende de:** T-22

- [x] SDK oficial `typesafe-sdk==0.7.0` (código do pacote lido antes da integração: cliente, perguntas, respostas, erros, retry e logging — em DEBUG ele registra corpos de requisição; sem conflito de dependências)
- [x] `backend/jevs/noul.json` (`ofensa`, `pii`), `choice.json` (`intencao` com as 4 rotas), `score.json` (`relevancia`, 5 níveis) no formato da API
- [x] `JevQuestions.load`: carga única e validação com os modelos Pydantic do SDK + conferência contra o grafo (fail-fast)
- [x] `JevJudge`:
  - [x] Noul: duas perguntas em uma requisição; bloqueia pelo maior valor ≥ `JEV_NOUL_THRESHOLD`; resposta ausente → `INDETERMINADO`
  - [x] Choice: `state` estruturado (`mensagem_atual` + `historico` recente); opção fora das rotas → `CONSULTA_RAG`
  - [x] Score: `state` com `pergunta` + `trechos` (fonte e texto); níveis 0–4 → nota 1–5; confiança < `JEV_MIN_CONFIDENCE` → fallback
  - [x] Log `jev_answer` só com metadados (versão do modelo, tokens, probabilidade/confiança)
- [x] Configuração: `JEV_PROVIDER`, `TYPESAFE_API_KEY` (`SecretStr`), `TYPESAFE_MODEL=jev-1.13.0` (versão fixada), `JEV_TIMEOUT_S`, `JEV_NOUL_THRESHOLD`, `JEV_MIN_CONFIDENCE`
- [x] Resiliência: timeout e `RetryPolicy` do SDK; conexão/timeout/429/5xx/resposta malformada → `503`; chave inválida → 500 com log
- [x] LGPD: logger `typesafe_sdk` fixado em `WARNING` (o SDK registra corpos de requisição em `debug`)
- [x] Cliente HTTP fechado no desligamento da API; `Dockerfile` copia `jevs/`; tipo `camada = "jev"` no frontend
- [x] Testes (51 novos): `test_jev_questions.py` (20 — arquivos, divergências do grafo, campo desconhecido, níveis → nota, escolha do motor) e `test_jev_judge.py` (31 — contrato da requisição, Noul/Choice/Score, grafo completo com `camada = "jev"`, regex e urgência sem chamar o Jev, 503 para conexão/timeout/429/5xx/malformada, 500 para chave inválida, LGPD nos logs, motor escolhido na inicialização) — passando pelo SDK real com `httpx2.MockTransport`; suíte: **251 passed**
- [x] **`JEV_PROVIDER=auto` como padrão** (Jev se houver chave; senão modo local) e registro da escolha no log de inicialização (`decision_engine_selected`) — AC-RF06-1, AC-RF06-2; verificado no container: `engine: llm`, `reason: auto: sem TYPESAFE_API_KEY`
- [x] `.env.example` com `JEV_PROVIDER=auto` e explicação

## T-24 — Verificação
**ACs:** AC-RF06-1..7 · **Depende de:** T-23

- [ ] Suíte completa sem Docker: **201 passed** (167 da v1 + 34 do Jev); build do frontend ok
- [ ] Stack real no Docker com o modo local: respostas e rotas inalteradas (bloqueio, urgência, agendamento, fora do escopo)
- [ ] CI simulado em ambiente limpo (`python:3.12-slim`) com a nova dependência
- [ ] Chamada real ao Jev — **pendente: requer `TYPESAFE_API_KEY` (acesso por lista de espera)**
- [ ] Avaliação com o dataset usando o Jev e comparação com o modo local (AC-RF06-7) — **pendente: requer chave**

## T-25 — Documentação final
**ACs:** — · **Depende de:** T-24

- [ ] README: Jev da TypeSafe AI como motor das decisões, modo local, configuração e LGPD; sem o termo antigo
- [ ] Explicação do fluxo das decisões (camada determinística → Jev → grafo) com os arquivos `jevs/*.json`
- [ ] Atualizar o índice e o status da SPEC ao concluir
