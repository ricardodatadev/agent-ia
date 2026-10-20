# Fase 4 — Tool calling (mock)

> SPEC: RF03, ADR-04, ADR-08

## T-09 — Contratos, mocks e nós das tools
**ACs:** AC-RF03-1, AC-RF03-2, AC-RF03-3, AC-RF03-4, AC-RF02-8 · **Depende de:** T-07

### Contratos (`tools.py`)
- [ ] Constante `ESPECIALIDADES` (mesma lista de `data/especialidades.md`)
- [ ] `AgendarConsultaArgs(especialidade: Literal[...])`
- [ ] `EncaminharAtendenteArgs(motivo: str 3–200, urgente: bool = False)`
- [ ] `ToolResult(tool, sucesso, protocolo, mensagem)`
- [ ] **Extra (ADR-08):** esquema exposto ao LLM com especialidade em texto livre + `normalize_especialidade` (sinônimos como "dentista", "médico do coração")

### Mocks
- [ ] `agendar_consulta_especialista(args) -> ToolResult` — protocolo `AGD-AAAAMMDD-XXXX`
- [ ] `encaminhar_atendente_humano(args) -> ToolResult` — protocolo `ATD-AAAAMMDD-XXXX`
- [ ] Sem I/O externo; sempre `sucesso = true`

### Nós do grafo
- [ ] `tool_agendamento`: `bind_tools` **somente** com `agendar_consulta_especialista`
- [ ] `tool_atendente`: `bind_tools` **somente** com `encaminhar_atendente_humano`
- [ ] Validar args com Pydantic **antes** de executar
- [ ] Especialidade ausente → pergunta de esclarecimento listando as especialidades; tool **não** executada
- [ ] Especialidade fora da lista → informa as disponíveis; tool **não** executada
- [ ] Sintomas de urgência → `urgente = true` (por palavra-chave, sem chamar o LLM)
- [ ] Resposta de `ATENDIMENTO_HUMANO` **sempre** contém orientação de ligar 192
- [ ] Resposta inclui o protocolo; `tool_call = {name, args, result}` no estado
- [ ] **Extra:** tool call com nome inesperado é ignorada; motivo inválido não impede o encaminhamento; menção a suicídio inclui CVV (188)

### Verificação
- [ ] AC-RF03-1: "quero marcar com um cardiologista" → `especialidade = "cardiologia"`, `sucesso = true`, protocolo na resposta (LLM falso)
- [ ] AC-RF03-2: "quero marcar uma consulta" → nenhuma tool, pede especialidade (LLM falso)
- [ ] AC-RF03-3: "quero marcar com um neurocirurgião" → nenhuma tool, lista disponíveis (LLM falso)
- [ ] AC-RF03-4: rota `ATENDIMENTO_HUMANO` → `encaminhar_atendente_humano` com `motivo`; `urgente = true` em urgência
- [ ] AC-RF02-8: resposta de urgência contém "192"
- [ ] Verificar extração de argumentos com Llama real: "cardiologista" → `cardiologia`; sem especialidade → pergunta; "neurocirurgião" → indisponível; motivo do atendente extraído corretamente
