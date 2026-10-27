# Fase 15 — Respostas de encaminhamento sem promessa de contato

> SPEC: RF03 · Origem: o usuário notou (2026-10-27) que a confirmação do agendamento dizia "a recepção vai entrar em contato", mas o assistente não coleta nenhum dado de contato.

## T-29 — Próximo passo que o paciente consegue cumprir
**ACs:** AC-RF03-5..6 · **Depende de:** T-28

> **Lacuna encontrada:** três textos fixos prometiam o que o sistema não faz: "a recepção vai entrar em contato" (agendamento), "alguém vai retornar em breve" (encaminhamento) e "encaminhei seu caso para a enfermagem" (urgência). Não há dado de contato, fila nem atendente no chat. Na urgência, a promessa vinha antes do 192 e podia fazer a pessoa esperar.

> **Decisão do usuário:** manter o "aguarde, alguém vai atender você aqui" pronto para uma futura transferência ao vivo, atrás de `HANDOFF_LIVE` (padrão `false`, porque hoje ninguém entra na conversa).

### Especificação (SPEC primeiro)
- [x] RF03: regra do próximo passo do paciente, `HANDOFF_LIVE` e urgência com 192 primeiro; AC-RF03-5..6; T-29 no plano e na matriz

### Código
- [x] `prompts.py`: `SCHEDULE_NEXT_STEP` e `HANDOFF_NEXT_STEP` (protocolo levado à recepção ou "aguarde"); `schedule_confirmed_reply` sem o "Pronto!" (é uma solicitação, nada foi marcado); `handoff_reply` urgente começa pelo `EMERGENCY_NOTICE` e nunca pede para aguardar
- [x] `config.py` (`handoff_live`), `GraphDeps.handoff_live`, `main.build_deps` e `.env.example` (`HANDOFF_LIVE=false`, com a explicação)

### Testes (330 → 335 passed)
- [x] `test_handoff_replies.py` (5): sem transferência ao vivo, nenhuma resposta promete contato e todas citam recepção e protocolo; com ela, "Aguarde"; urgência começa pelo 192 e não pede para aguardar nos dois modos; o grafo respeita a configuração

### Verificação
- [x] Suíte completa: **335 passed**
- [x] README: limitação de escopo explicada e transferência ao vivo nos próximos passos
