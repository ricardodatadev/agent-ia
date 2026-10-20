# Fase 6 — Frontend (React + Tailwind)

> SPEC: RF04, §5.3 (contrato da API)

## T-11 — Interface de chat
**ACs:** AC-RF04-1, AC-RF04-2, AC-RF04-3, AC-RF04-4 · **Depende de:** T-01 (contrato)

### Setup
- [x] Projeto Vite + React + TypeScript + Tailwind em `frontend/` (React 19.3, Vite 8.3, Tailwind 4.3, TypeScript 5.9 — versões fixadas)
- [x] URL da API via variável de ambiente (`VITE_API_URL`, padrão `http://localhost:8000`)
- [x] Tipos TS espelhando `ChatRequest` / `ChatResponse` da SPEC §5.3

### Componentes
- [x] `api.ts` — `sendMessage(message, history)` enviando as **últimas 6 mensagens** (timeout de 300 s, já no valor ajustado da T-12 para CPU)
- [x] `ChatWindow` — lista de mensagens com scroll automático (+ estado vazio com sugestões clicáveis)
- [x] `MessageBubble` — mensagem do usuário / assistente
- [x] `Badges`:
  - [x] 🛡️ Guardrail (vermelho/âmbar) quando `route = "BLOQUEIO"`, com o motivo
  - [x] 🔧 Ação (azul) quando `tool_call != null`, com nome da ferramenta e protocolo (+ "prioridade" se urgente)
  - [x] 📄 Fontes (lista recolhível) quando `sources` não vazio
  - [x] ℹ️ Sem evidência quando `fallback = true`
  - [x] **Extra:** linha discreta com a rota e a nota de relevância (útil para demonstrar o grafo)
- [x] Input com envio por Enter e botão; desabilitado durante o carregamento (Shift+Enter quebra linha; contador 0/1000)

### Estados
- [x] Loading enquanto aguarda resposta (indicador de digitação)
- [x] Erro de rede/`503` → mensagem amigável + botão de reenviar; histórico preservado
- [x] Histórico só em memória (recarregar limpa)
- [x] **Extra (privacidade):** mensagens bloqueadas não entram no histórico enviado; backend também descarta turnos com PII (regex) — teste em `test_api.py`

### Avisos
- [x] Aviso fixo: "Este assistente não substitui atendimento médico. Em emergência, ligue 192."

### Verificação (automatizada com Edge headless + Playwright + backend real com LLM falso, viewport 375×812 — 12/12 em 20/10)
- [x] AC-RF04-1: mensagem bloqueada exibe badge de guardrail com motivo (PII e ofensa)
- [x] AC-RF04-2: resposta com tool exibe badge de ação com nome e protocolo (agendamento e urgência)
- [x] AC-RF04-3: com backend parado, UI mostra erro e mantém histórico (botão "Tentar novamente")
- [x] AC-RF04-4: utilizável em 375px de largura (sem scroll horizontal: `scrollWidth = 375`)
- [x] **Achado na verificação:** selos de guardrail e de ação quebravam linha de forma ruim em 375 px (protocolo em 3 linhas) → selos com quebra controlada e protocolo sem quebra
- [x] `npm run build` (typecheck + build) sem erros
- [ ] Verificação com Ollama real na UI (Edge headless, stack do compose) e screenshot em `docs/screenshot.png` — **pendente: depende da stack completa no Docker (T-12)**
