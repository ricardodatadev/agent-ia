import type { Message } from "../types";
import { ResponseBadges } from "./Badges";

export function MessageBubble({ message, onRetry }: { message: Message; onRetry: (text: string) => void }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-teal-700 px-4 py-2.5 text-[15px] text-white shadow-sm">
          {message.content}
        </p>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div role="alert" className="mr-auto flex max-w-[85%] flex-col items-start gap-2 rounded-2xl rounded-bl-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        <p>{message.content}</p>
        <button
          type="button"
          onClick={() => onRetry(message.retryText)}
          className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-red-700 ring-1 ring-red-200 hover:bg-red-100"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5">
      <Avatar />
      <div className="max-w-[85%] rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-slate-800">{message.content}</p>
        <ResponseBadges response={message.response} />
      </div>
    </div>
  );
}

export function Avatar() {
  return (
    <div aria-hidden className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-700 text-white shadow-sm">
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
        <path d="M9.5 4h5v5.5H20v5h-5.5V20h-5v-5.5H4v-5h5.5z" />
      </svg>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex items-start gap-2.5" aria-live="polite" aria-label="O assistente está digitando">
      <Avatar />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="h-2 w-2 animate-bounce rounded-full bg-teal-600/70" style={{ animationDelay: `${delay}ms` }} />
        ))}
      </div>
    </div>
  );
}
