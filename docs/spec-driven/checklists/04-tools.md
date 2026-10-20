# Fase 4 — Tool calling (mock)

> SPEC: RF03, ADR-04, ADR-08

## T-09 — Contratos, mocks e nós das tools
**ACs:** AC-RF03-1, AC-RF03-2, AC-RF03-3, AC-RF03-4, AC-RF02-8 · **Depende de:** T-07

### Contratos (`tools.py`)
- [x] Constante `ESPECIALIDADES` (mesma lista de `data/especialidades.md`)
- [x] `AgendarConsultaArgs(especialidade: Literal[...])`
- [x] `EncaminharAtendenteArgs(motivo: str 3–200, urgente: bool = False)`
- [x] `ToolResult(tool, sucesso, protocolo, mensagem)`
- [x] **Extra (ADR-08):** esquema exposto ao LLM com especialidade em texto livre + `normalize_especialidade` (sinônimos como "dentista", "médico do coração")

### Mocks
- [x] `agendar_consulta_especialista(args) -> ToolResult` — protocolo `AGD-AAAAMMDD-XXXX`
- [x] `encaminhar_atendente_humano(args) -> ToolResult` — protocolo `ATD-AAAAMMDD-XXXX`
- [x] Sem I/O externo; sempre `sucesso = true`

### Nós do grafo
- [x] `tool_agendamento`: `bind_tools` **somente** com `agendar_consulta_especialista`
- [x] `tool_atendente`: `bind_tools` **somente** com `encaminhar_atendente_humano`
- [x] Validar args com Pydantic **antes** de executar
- [x] Especialidade ausente → pergunta de esclarecimento listando as especialidades; tool **não** executada
- [x] Especialidade fora da lista → informa as disponíveis; tool **não** executada
- [x] Sintomas de urgência → `urgente = true` (por palavra-chave, sem chamar o LLM)
- [x] Resposta de `ATENDIMENTO_HUMANO` **sempre** contém orientação de ligar 192
- [x] Resposta inclui o protocolo; `tool_call = {name, args, result}` no estado
- [x] **Extra:** tool call com nome inesperado é ignorada; motivo inválido não impede o encaminhamento; menção a suicídio inclui CVV (188)
- [x] **Extra:** especialidades que exigem avaliação prévia do clínico geral (cardiologia, dermatologia, psicologia, nutrição — `data/especialidades.md`) avisam isso na confirmação; ausente × indisponível têm respostas diferentes

### Verificação
- [x] AC-RF03-1: "quero marcar com um cardiologista" → `especialidade = "cardiologia"`, `sucesso = true`, protocolo na resposta (LLM falso)
- [x] AC-RF03-2: "quero marcar uma consulta" → nenhuma tool, pede especialidade (LLM falso)
- [x] AC-RF03-3: "quero marcar com um neurocirurgião" → nenhuma tool, lista disponíveis (LLM falso)
- [x] AC-RF03-4: rota `ATENDIMENTO_HUMANO` → `encaminhar_atendente_humano` com `motivo`; `urgente = true` em urgência
- [x] AC-RF02-8: resposta de urgência contém "192"
- [x] Verificar extração de argumentos com Llama real: "cardiologista" → `cardiologia`; sem especialidade → pergunta; "neurocirurgião" → indisponível; motivo do atendente extraído corretamente — verificado pela API em 20/10: os 4 casos corretos, mais "preciso de um dentista" → `odontologia` e o follow-up "dentista" (após o assistente pedir a especialidade) → `odontologia`; urgência encaminhada em 5 s sem chamar a tool
