import { useState } from "react";
import { ApiError, buildHistory, sendMessage } from "./api";
import { ChatWindow } from "./components/ChatWindow";
import { Composer } from "./components/Composer";
import type { Message } from "./types";

const newId = () => crypto.randomUUID();

export default function App() {
  // Histórico só em memória: recarregar a página limpa a conversa (LGPD, SPEC P03).
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  async function ask(text: string, userId: string, previous: Message[]) {
    setLoading(true);
    try {
      const response = await sendMessage(text, buildHistory(previous));
      setMessages((current) => [
        ...current.map((m) => (m.id === userId && m.role === "user" ? { ...m, blocked: response.route === "BLOQUEIO" } : m)),
        { id: newId(), role: "assistant", content: response.reply, response },
      ]);
    } catch (err) {
      const content = err instanceof ApiError ? err.message : "Algo deu errado. Tente novamente.";
      setMessages((current) => [...current, { id: newId(), role: "error", content, retryText: text }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSend(text: string) {
    if (loading) return;
    const previous = messages.filter((m) => m.role !== "error");
    const user: Message = { id: newId(), role: "user", content: text };
    setMessages([...previous, user]);
    void ask(text, user.id, previous);
  }

  function handleRetry(text: string) {
    if (loading) return;
    // A mensagem do paciente continua na tela; só o aviso de erro sai.
    const kept = messages.filter((m) => m.role !== "error");
    const lastUser = [...kept].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages(kept);
    void ask(text, lastUser.id, kept.slice(0, kept.indexOf(lastUser)));
  }

  return (
    <div className="flex min-h-dvh flex-col bg-gradient-to-b from-teal-50 via-slate-50 to-slate-100 text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-700 text-white shadow-sm">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden>
              <path d="M9.5 4h5v5.5H20v5h-5.5V20h-5v-5.5H4v-5h5.5z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold leading-tight">Assistente UBS · Agente de IA</h1>
            <p className="truncate text-xs text-slate-500">UBS Jardim Esperança · demonstração com dados fictícios</p>
          </div>
          <span className="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> RAG · Guardrails · Tools
          </span>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
        <ChatWindow messages={messages} loading={loading} onSend={handleSend} onRetry={handleRetry} />
      </main>

      <footer className="sticky bottom-0 bg-gradient-to-t from-slate-100 via-slate-100/95 to-transparent pt-4">
        <div className="mx-auto max-w-3xl px-4 pb-3">
          <Composer disabled={loading} onSend={handleSend} />
          <p className="mt-2 text-center text-xs text-slate-500">
            <span aria-hidden>⚠️</span> Este assistente não substitui atendimento médico. Em emergência, ligue{" "}
            <strong className="text-red-700">192</strong>.
          </p>
        </div>
      </footer>
    </div>
  );
}
