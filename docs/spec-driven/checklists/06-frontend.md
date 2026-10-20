# Fase 6 — Frontend (React + Tailwind)

> SPEC: RF04, §5.3 (contrato da API)

## T-11 — Interface de chat
**ACs:** AC-RF04-1, AC-RF04-2, AC-RF04-3, AC-RF04-4 · **Depende de:** T-01 (contrato)

### Setup
- [ ] Projeto Vite + React + TypeScript + Tailwind em `frontend/` (React 19.3, Vite 8.3, Tailwind 4.3, TypeScript 5.9 — versões fixadas)
- [ ] URL da API via variável de ambiente (`VITE_API_URL`, padrão `http://localhost:8000`)
- [ ] Tipos TS espelhando `ChatRequest` / `ChatResponse` da SPEC §5.3

### Componentes
- [ ] `api.ts` — `sendMessage(message, history)` enviando as **últimas 6 mensagens** (timeout de 120 s)
- [ ] `ChatWindow` — lista de mensagens com scroll automático (+ estado vazio com sugestões clicáveis)
- [ ] `MessageBubble` — mensagem do usuário / assistente
- [ ] `Badges`:
  - [ ] 🛡️ Guardrail (vermelho/âmbar) quando `route = "BLOQUEIO"`, com o motivo
  - [ ] 🔧 Ação (azul) quando `tool_call != null`, com nome da ferramenta e protocolo (+ "prioridade" se urgente)
  - [ ] 📄 Fontes (lista recolhível) quando `sources` não vazio
  - [ ] ℹ️ Sem evidência quando `fallback = true`
  - [ ] **Extra:** linha discreta com a rota e a nota de relevância (útil para demonstrar o grafo)
- [ ] Input com envio por Enter e botão; desabilitado durante o carregamento (Shift+Enter quebra linha; contador 0/1000)

### Estados
- [ ] Loading enquanto aguarda resposta (indicador de digitação)
- [ ] Erro de rede/`503` → mensagem amigável + botão de reenviar; histórico preservado
- [ ] Histórico só em memória (recarregar limpa)
- [ ] **Extra (privacidade):** mensagens bloqueadas não entram no histórico enviado; backend também descarta turnos com PII (regex) — teste em `test_api.py`

### Avisos
- [ ] Aviso fixo: "Este assistente não substitui atendimento médico. Em emergência, ligue 192."

### Verificação (automatizada com Edge headless + backend real com LLM falso, viewport 375×812)
- [ ] AC-RF04-1: mensagem bloqueada exibe badge de guardrail com motivo (PII e ofensa)
- [ ] AC-RF04-2: resposta com tool exibe badge de ação com nome e protocolo (agendamento e urgência)
- [ ] AC-RF04-3: com backend parado, UI mostra erro e mantém histórico (botão "Tentar novamente")
- [ ] AC-RF04-4: utilizável em 375px de largura (sem scroll horizontal)
- [ ] `npm run build` (typecheck + build) sem erros
- [ ] Verificação com Ollama real na UI (Edge headless, stack do compose): RAG com fontes e relevância 5/5 (72 s), urgência com prioridade e 192 (4 s), CPF bloqueado com badge LGPD (1 s) — screenshot em `docs/screenshot.png`
