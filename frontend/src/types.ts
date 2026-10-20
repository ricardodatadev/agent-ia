// Espelho do contrato de POST /chat (SPEC §5.3 / backend/app/models.py)

export type Route = "BLOQUEIO" | "CONSULTA_RAG" | "AGENDAMENTO" | "ATENDIMENTO_HUMANO" | "FORA_DO_NICHO";
export type BlockReason = "OFENSA" | "PII" | "INDETERMINADO";
export type GuardrailLayer = "regex" | "llm" | "jev";
export type ToolName = "agendar_consulta_especialista" | "encaminhar_atendente_humano";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  message: string;
  history: ChatTurn[];
}

export interface GuardrailResult {
  motivo: BlockReason;
  camada: GuardrailLayer;
}

export interface ToolResult {
  tool: ToolName;
  sucesso: boolean;
  protocolo: string;
  mensagem: string;
}

export interface ToolCallInfo {
  name: ToolName;
  args: Record<string, unknown>;
  result: ToolResult;
}

export interface Source {
  source: string;
  section: string | null;
  snippet: string;
}

export interface ChatResponse {
  request_id: string;
  reply: string;
  route: Route;
  guardrail: GuardrailResult | null;
  tool_call: ToolCallInfo | null;
  score: number | null;
  fallback: boolean;
  sources: Source[];
}

// Estado da interface
export type Message =
  | { id: string; role: "user"; content: string; blocked?: boolean }
  | { id: string; role: "assistant"; content: string; response: ChatResponse }
  | { id: string; role: "error"; content: string; retryText: string };
