import type { ReactNode } from "react";
import type { BlockReason, ChatResponse, GuardrailLayer, Route, Source, ToolCallInfo } from "../types";

const BLOCK_LABELS: Record<BlockReason, string> = {
  OFENSA: "Linguagem ofensiva",
  PII: "Dados pessoais (LGPD)",
  INDETERMINADO: "Não foi possível validar",
};

const LAYER_LABELS: Record<GuardrailLayer, string> = {
  regex: "regra",
  llm: "IA",
  jev: "Jev",
};

const ROUTE_LABELS: Record<Route, string> = {
  BLOQUEIO: "Bloqueio",
  CONSULTA_RAG: "Consulta aos documentos",
  AGENDAMENTO: "Agendamento",
  ATENDIMENTO_HUMANO: "Atendimento humano",
  FORA_DO_NICHO: "Fora do escopo",
};

function Pill({ className, children, title }: { className: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex max-w-full flex-wrap items-center gap-x-1.5 gap-y-0.5 rounded-xl px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${className}`}>
      {children}
    </span>
  );
}

export function GuardrailBadge({ motivo, camada }: { motivo: BlockReason; camada: GuardrailLayer }) {
  const tone = motivo === "OFENSA" ? "bg-red-50 text-red-700 ring-red-200" : "bg-amber-50 text-amber-800 ring-amber-200";
  return (
    <Pill className={tone} title={`Bloqueado antes de qualquer busca ou geração (camada: ${LAYER_LABELS[camada]})`}>
      <span aria-hidden>🛡️</span>
      <span>Guardrail · {BLOCK_LABELS[motivo]}</span>
      <span className="whitespace-nowrap opacity-60">· {LAYER_LABELS[camada]}</span>
    </Pill>
  );
}

export function ToolBadge({ toolCall }: { toolCall: ToolCallInfo }) {
  const urgent = toolCall.args.urgente === true;
  const label = toolCall.name === "agendar_consulta_especialista" ? "Consulta solicitada" : "Encaminhado à equipe";
  return (
    <Pill className="bg-sky-50 text-sky-800 ring-sky-200" title={`Ferramenta: ${toolCall.name}`}>
      <span aria-hidden>🔧</span>
      <span className="whitespace-nowrap">{label}</span>
      <span className="whitespace-nowrap font-mono text-[11px]">{toolCall.result.protocolo}</span>
      {urgent && <span className="rounded-full bg-red-600 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-white">prioridade</span>}
    </Pill>
  );
}

export function NoEvidenceBadge() {
  return (
    <Pill className="bg-slate-100 text-slate-600 ring-slate-200" title="Os documentos da UBS não trazem essa informação; nenhuma resposta foi gerada">
      <span aria-hidden>ℹ️</span> Sem evidência nos documentos
    </Pill>
  );
}

function lastSection(section: string | null): string | null {
  return section ? section.split(" › ").slice(-1)[0] : null;
}

export function SourcesList({ sources }: { sources: Source[] }) {
  return (
    <details className="group mt-1 text-xs text-slate-600">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full px-2.5 py-1 font-medium text-teal-800 ring-1 ring-teal-200 ring-inset hover:bg-teal-50">
        <span aria-hidden>📄</span> Fontes ({sources.length})
        <span className="transition-transform group-open:rotate-180" aria-hidden>▾</span>
      </summary>
      <ul className="mt-2 space-y-2">
        {sources.map((s, i) => (
          <li key={`${s.source}-${i}`} className="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
            <p className="font-medium text-slate-700">
              {s.source}
              {lastSection(s.section) && <span className="font-normal text-slate-500"> · {lastSection(s.section)}</span>}
            </p>
            <p className="mt-1 line-clamp-3 text-slate-500">{s.snippet}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function DebugLine({ response }: { response: ChatResponse }) {
  return (
    <p className="text-[11px] text-slate-400">
      Rota: {ROUTE_LABELS[response.route]}
      {response.score !== null && <> · relevância {response.score}/5</>}
    </p>
  );
}

export function ResponseBadges({ response }: { response: ChatResponse }) {
  const hasPills = response.guardrail || response.tool_call || response.fallback;
  return (
    <div className="mt-2 space-y-1.5">
      {hasPills && (
        <div className="flex flex-wrap gap-1.5">
          {response.guardrail && <GuardrailBadge {...response.guardrail} />}
          {response.tool_call && <ToolBadge toolCall={response.tool_call} />}
          {response.fallback && <NoEvidenceBadge />}
        </div>
      )}
      {response.sources.length > 0 && <SourcesList sources={response.sources} />}
      <DebugLine response={response} />
    </div>
  );
}
