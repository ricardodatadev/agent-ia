import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { MessageBubble, TypingIndicator } from "./MessageBubble";

const SUGGESTIONS = [
  "Qual o horário da vacina da gripe?",
  "Preciso de jejum para exame de sangue?",
  "Quero marcar com um cardiologista",
  "Quais são os sintomas da dengue?",
];

interface Props {
  messages: Message[];
  loading: boolean;
  onSend: (text: string) => void;
  onRetry: (text: string) => void;
}

export function ChatWindow({ messages, loading, onSend, onRetry }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-2 py-10 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-700 text-white shadow-md">
          <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor" aria-hidden>
            <path d="M9.5 4h5v5.5H20v5h-5.5V20h-5v-5.5H4v-5h5.5z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-slate-800">Olá! Como posso ajudar?</h2>
        <p className="mt-1 max-w-sm text-sm text-slate-500">
          Tiro dúvidas com base nos documentos da UBS, agendo consultas e encaminho você para a equipe.
        </p>
        <div className="mt-6 grid w-full max-w-md gap-2 sm:grid-cols-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSend(s)}
              disabled={loading}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 shadow-sm transition hover:border-teal-400 hover:bg-teal-50"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 py-4" aria-live="polite">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onRetry={onRetry} />
      ))}
      {loading && <TypingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
