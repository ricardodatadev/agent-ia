# Especificação de Requisitos: Assistente UBS · Agente de IA (`agent-ia`)

## 1. Visão Geral e Objetivo

Desenvolver um agente de IA para atendimento ao paciente em uma Unidade Básica de Saúde (UBS). O sistema faz a triagem das mensagens e responde dúvidas sobre serviços de saúde, horários de vacinação, exames e especialidades da unidade usando **RAG (Retrieval-Augmented Generation)**.

As decisões do fluxo são tomadas pelo **Jev**, o modelo de decisões tipadas da **TypeSafe AI** (*System One*). Em vez de gerar texto, o Jev responde perguntas fechadas sobre um `state` com três primitivas: **Noul** (sim/não, com probabilidade), **Choice** (uma opção de uma lista fechada, com confiança) e **Score** (um nível em uma escala ordenada, com confiança). Executadas cedo no **LangGraph**, essas decisões economizam tokens e garantem conformidade:
- Bloqueando ofensas e profanidades;
- Impedindo o envio ou a solicitação de dados pessoais sensíveis (LGPD/PII);
- Direcionando o fluxo (RAG, agendamento, atendimento humano/enfermagem ou fora do escopo) e acionando **Tool Calling** (mockado);
- Só gerando resposta quando os documentos recuperados sustentam a resposta.

Referência do Jev: [docs.typesafe.ai](https://docs.typesafe.ai/introduction) · API `POST /v1/systemone` · SDK oficial `typesafe-sdk`.

---

## 2. Casos de Uso do Nicho (UBS / Saúde)

*   **Dúvidas Frequentes & Protocolos (RAG):** Documentos da UBS com horários de atendimento, documentos necessários para consulta, calendário de vacinação, preparação para exames simples e campanhas de saúde.
*   **Encaminhamento para Agendamento (Tool Calling):** Quando o usuário expressa intenção clara de marcar consulta com especialista.
*   **Encaminhamento para Atendente/Enfermagem (Tool Calling):** Quando o usuário reporta sintomas urgentes ou precisa de atendimento presencial imediato.
*   **Proteção de Dados Pessoais (LGPD / PII):** Interceptação imediata caso o usuário envie CPFs, nomes completos de terceiros, exames ou solicite histórico médico de outros pacientes.

---

## 3. Requisitos Funcionais (RF)

| ID | Requisito | Descrição |
| :--- | :--- | :--- |
| **RF01** | **Ingestão e Chunking (RAG / Qdrant)** | Script em Python (`scripts/ingest.py`) para processar e criar chunks dos manuais/protocolos da UBS e persistir no Qdrant com embeddings. |
| **RF02** | **Triagem e Guardrails com Jev** | Decisões Noul, Choice e Score tomadas pelo Jev (TypeSafe AI) no fluxo do LangGraph, precedidas por regras determinísticas (detalhado abaixo). |
| **RF03** | **Function / Tool Calling (Extensível & Leve)** | Apenas os contratos de chamada de ferramentas para `agendar_consulta_especialista(especialidade)` e `encaminhar_atendente_humano(motivo)`. As funções retornam respostas simuladas (mocks) com sucesso de execução. |
| **RF04** | **Interface de Chat (React)** | Interface simples contendo histórico do diálogo, indicação visual quando uma Tool/Ação é disparada ou quando um Guardrail intercepta a mensagem. |
| **RF05** | **Execução Unificada em Docker** | Subida em ambiente local via `docker compose up`. |
| **RF06** | **LLM e motor de decisões configuráveis** | Pelo `.env`: o LLM que gera respostas (Ollama local com Llama ou Qwen, API do Claude ou API do Gemini) e o motor de decisões (Jev ou modo local). Detalhado na seção 7. |

### Detalhamento da Triagem e Guardrails com Jev (RF02)

Cada decisão começa por uma **camada determinística** (regra fixa, zero tokens) e só então consulta o Jev.

1.  **Noul (Sim / Não):** Segurança de entrada, de baixa latência e baixo custo.
    *   **Camada determinística:** regex de CPF, Cartão SUS, RG, telefone e e-mail → bloqueia sem chamar o Jev.
    *   **Jev:** duas perguntas Noul na mesma requisição, `ofensa` e `pii`. Bloqueia se a probabilidade de qualquer uma atingir o limite configurado (padrão 0,5).
    *   **Ofensa** → encerra com mensagem de respeito. **PII** → encerra informando o protocolo de privacidade da UBS.
2.  **Choice (Direcionamento de Fluxo / Intent Classification):** Classifica a intenção para roteamento determinístico no LangGraph.
    *   **Camada determinística:** termos de urgência ("dor no peito", "falta de ar", "desmaio"…) → `ATENDIMENTO_HUMANO` sem chamar o Jev.
    *   **Jev:** uma pergunta Choice, `intencao`, cujas opções são exatamente as rotas do grafo:
        *   `CONSULTA_RAG`: pergunta sobre funcionamento, vacinas ou exames da UBS.
        *   `AGENDAMENTO`: intenção de marcar consulta/especialista → aciona a Tool de Agendamento.
        *   `ATENDIMENTO_HUMANO`: sintomas urgentes ou questões administrativas complexas → aciona a Tool de Atendimento/Enfermagem.
        *   `FORA_DO_NICHO`: perguntas sem relação com saúde/UBS → resposta padrão e encerra.
    *   O `state` enviado é estruturado: `mensagem_atual` + `historico` recente (para continuações como "e para pediatra?").
3.  **Score (Nota 1 a 5):** Relevância do contexto recuperado no Qdrant em relação à pergunta.
    *   **Jev:** uma pergunta Score, `relevancia`, com 5 níveis (0 a 4) → nota 1 a 5. O `state` traz `pergunta` + `trechos` com a fonte de cada um.
    *   Se **Score < 3**, ou se a confiança do Jev estiver abaixo do mínimo configurado, aciona o *fallback* antes de responder.

**Falha segura:** resposta ausente ou fora do formato → Noul bloqueia, Choice segue para `CONSULTA_RAG` (o Score ainda protege) e Score vai para o fallback. Indisponibilidade do Jev → `503` amigável.

---

## 4. Arquitetura do Grafo no LangGraph (Com Economia de Tokens via Jev)

```text
                       [ Entrada do Usuário ]
                                  │
                                  ▼
               [ Noul: regex de PII  →  Jev (ofensa, pii) ]
                      (Segurança rápida e baixo custo)
                             /         \
                      (Bloqueio)     (Aprovado)
                           /             \
                          ▼               ▼
                 [ Resposta Guardrail ]  [ Choice: termos de urgência  →  Jev (intencao) ]
                 ("Mensagem bloqueada")       /         │          \           \
                                             /          │           \           \
                             AGENDAMENTO    /   CONSULTA_RAG   ATENDIMENTO_HUMANO  FORA_DO_NICHO
                                           /            │            \               \
                                          ▼             ▼             ▼               ▼
                           [ Tool: Agendamento ]   [ RAG Qdrant ]  [ Tool: Atendente ]  [ Resposta padrão ]
                                                        │
                                                        ▼
                                          [ Score: Jev (relevancia) ]
                                            (Contexto vs Pergunta)
                                                  /          \
                                             (≥ 3)          (< 3)
                                               ▼               ▼
                                     [ Resposta do LLM ]   [ Fallback ]
```

O **LangGraph** é o fluxo: cada nó lê o estado do grafo, monta o `state` do Jev, chama a API e grava a decisão de volta no estado; as arestas condicionais leem essa decisão e escolhem o próximo nó. O **Jev** é o motor de decisão de cada ponto de controle. O **LLM** só escreve texto na última etapa (e extrai argumentos das tools).

---

## 5. Estrutura do Repositório (`agent-ia`)

```text
agent-ia/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI (/chat, /health), logs estruturados, 503 amigável
│   │   ├── graph.py         # Grafo de estados com LangGraph
│   │   ├── guardrails.py    # Camadas determinísticas (regex de PII, urgência) + orquestração das decisões
│   │   ├── judge.py         # Interface das decisões (Protocol) + modo local com LLM
│   │   ├── jev.py           # Cliente do Jev (SDK oficial): Noul, Choice, Score
│   │   ├── rag.py           # Ingestão e busca vetorial no Qdrant
│   │   ├── tools.py         # Mocks de Tool/Function Calling (Agendamento, Atendimento)
│   │   ├── llm.py           # Fábrica do LLM (Ollama, Claude, Gemini) e embeddings
│   │   ├── prompts.py       # Prompts e textos fixos do domínio
│   │   ├── config.py        # Configuração por variáveis de ambiente
│   │   └── models.py        # Schemas Pydantic tipados
│   ├── jevs/                # Perguntas do Jev (noul.json, choice.json, score.json)
│   ├── data/                # Documentos/manuais da UBS (Exames, Vacinas, Regras)
│   ├── scripts/
│   │   └── ingest.py        # Chunking + Embeddings + Carga Qdrant
│   ├── tests/               # unit/, integration/, eval/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/                 # Chat em React + Tailwind
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml       # Orquestração (Ollama + Qdrant + FastAPI + React)
└── README.md                # Documentação técnica e guia de execução
```

---

## 6. Boas Práticas de Implementação do Jev (padrão de mercado em Python)

| Prática | Como se aplica |
| :--- | :--- |
| **SDK oficial com versão fixada** | `typesafe-sdk` fixado em uma versão publicada há mais de duas semanas, em vez de chamadas HTTP escritas à mão. |
| **Perguntas como configuração versionada** | `backend/jevs/*.json` no formato da API (`type`, `instructions`, `criteria`), revisáveis sem mexer em código. |
| **Validação na inicialização (fail-fast)** | Os arquivos são carregados **uma vez** e validados com os modelos Pydantic do SDK. As opções do Choice são conferidas contra as rotas do grafo e o Score precisa ter 5 níveis: divergência impede a subida do backend, em vez de falhar no meio de um atendimento. |
| **Entradas e saídas tipadas** | Requisição montada com objetos tipados do SDK; resposta lida por tipo (`nouls`, `choices`, `scores`), sem acessar dicionários soltos. |
| **Modelo fixado por versão** | `TYPESAFE_MODEL=jev-1.13.0` em vez do alias `jev-latest`, que muda de versão sem aviso; a versão que respondeu é registrada no log. |
| **Limiares explícitos e configuráveis** | Probabilidade de bloqueio do Noul e confiança mínima do Score definidas no `.env` e ajustadas com o dataset de avaliação. |
| **Resiliência** | Timeout por chamada, retries com backoff do SDK (429, 408, 5xx) e orçamento total por chamada. Indisponibilidade → `503`; chave inválida → erro de configuração registrado no log. |
| **Falha segura** | Toda resposta ausente, fora das opções ou de baixa confiança cai no caminho seguro (ver RF02). |
| **Privacidade (LGPD)** | O logger do SDK nunca roda em `debug` (ele registra corpos de requisição); os logs da aplicação registram só metadados da decisão (versão, tokens, probabilidade/confiança), nunca o texto. |
| **Inversão de dependência** | O grafo depende de uma interface (`Judge`), não do provedor: o Jev e o modo local são intercambiáveis e testáveis isoladamente. |
| **Testes sem rede, pelo SDK real** | Testes passam pelo SDK oficial com transporte HTTP simulado (`httpx2.MockTransport`), conferindo o contrato da requisição e cada caminho de decisão. |
| **Avaliação com dataset** | O mesmo dataset rotulado mede cada decisão com o Jev e com o modo local, antes de qualquer troca de modelo ou limiar. |

---

## 7. Configuração (.env)

### Motor de decisões (Noul, Choice, Score)

| `JEV_PROVIDER` | Comportamento |
| :--- | :--- |
| `auto` (padrão) | Usa o **Jev** se `TYPESAFE_API_KEY` estiver definida; caso contrário, o **modo local**. |
| `typesafe` | Exige o Jev; sem chave, o backend não sobe (erro claro). |
| `llm` | Força o **modo local**: o LLM configurado responde às mesmas perguntas em JSON validado, com conferência de evidência no Score. Útil para desenvolvimento, uso offline ou sem acesso ao Jev (lista de espera). |

Demais variáveis do Jev: `TYPESAFE_API_KEY`, `TYPESAFE_MODEL`, `JEV_TIMEOUT_S`, `JEV_NOUL_THRESHOLD`, `JEV_MIN_CONFIDENCE`.

### LLM (geração de respostas, argumentos das tools e modo local)

O `.env.example` mantém blocos comentados para o usuário escolher um provedor:

| Opção | `LLM_PROVIDER` / `LLM_MODEL` |
| :--- | :--- |
| Llama 3.2 3B (padrão) | `ollama` / `llama3.2:3b` |
| Llama 3.1 8B | `ollama` / `llama3.1:8b` |
| Qwen 2.5 3B | `ollama` / `qwen2.5:3b` |
| Qwen 2.5 1.5B | `ollama` / `qwen2.5:1.5b` |
| Claude | `anthropic` / `claude-opus-5-5` + `ANTHROPIC_API_KEY` |
| Gemini | `google` / `gemini-2.5-flash` + `GOOGLE_API_KEY` |

Embeddings (`bge-m3`) e Qdrant são sempre locais.

**LGPD:** com o Jev, Claude ou Gemini, as mensagens são enviadas a serviços externos. Com Ollama e modo local, nada sai da máquina.

---

## 8. Por que esta estrutura impressiona o recrutador?

1. **Decisões com o modelo certo para cada tarefa:** o Jev decide (Noul, Choice, Score) com probabilidade e confiança, e o LLM só escreve texto quando necessário. É uma separação de responsabilidades que reduz custo, latência e alucinação.
2. **Economia de tokens e latência:** regras determinísticas e o Jev executados antes da busca RAG e da geração evitam chamadas caras e desnecessárias quando a entrada é inadequada ou fora do escopo.
3. **Padrões de engenharia sênior:** SDK oficial, configuração versionada e validada na inicialização, versões fixadas, resiliência, falha segura, LGPD nos logs, inversão de dependência e testes pelo SDK real.
4. **Design genérico e reutilizável:** trocar `data/`, os arquivos de `jevs/` e os prompts aplica o mesmo agente em e-commerce, suporte financeiro ou RH.
5. **Tool calling limpo:** conecta o LLM a ações do mundo real de forma controlada e segura, sem complexidade de orquestração multiagente.
