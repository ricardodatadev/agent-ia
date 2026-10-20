import type { ChatResponse, ChatTurn, Message } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const MAX_MESSAGE_CHARS = 1000;
const MAX_HISTORY = 6;
const TIMEOUT_MS = 300_000; // LLM local em CPU: respostas RAG podem passar de 1 minuto

export class ApiError extends Error {}

/**
 * Últimas 6 mensagens válidas da conversa. Mensagens bloqueadas (e a resposta de bloqueio)
 * e erros não entram — o backend também descarta turnos com dados pessoais.
 */
export function buildHistory(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === "user" && !m.blocked) turns.push({ role: "user", content: m.content });
    if (m.role === "assistant" && m.response.route !== "BLOQUEIO") turns.push({ role: "assistant", content: m.content });
  }
  return turns.slice(-MAX_HISTORY);
}

export async function sendMessage(message: string, history: ChatTurn[]): Promise<ChatResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal: controller.signal,
    });
    if (res.status === 503) throw new ApiError("O assistente está temporariamente indisponível. Tente novamente em instantes.");
    if (res.status === 422) throw new ApiError("Mensagem inválida. Escreva até 1000 caracteres.");
    if (!res.ok) throw new ApiError("Não foi possível obter uma resposta agora.");
    return (await res.json()) as ChatResponse;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("A resposta demorou mais que o esperado. Tente novamente.");
    }
    throw new ApiError("Sem conexão com o assistente. Verifique se o serviço está no ar e tente novamente.");
  } finally {
    clearTimeout(timer);
  }
}
