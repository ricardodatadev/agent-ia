"""Avaliação com LLM real (SPEC §7.3): roda o dataset pelo grafo e mede as metas da SPEC.

Uso (com Qdrant e Ollama no ar):
    python tests/eval/run_eval.py                 # dataset completo (50 casos)
    python tests/eval/run_eval.py --only rag-01,nc-02 --label teste
    python tests/eval/run_eval.py --dataset tests/eval/dataset_robustez.jsonl --label robustez  # urgência e PII
Resultados em tests/eval/results/ (ignorado pelo git) e tabela Markdown no terminal.
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parents[1]))

DATASET = EVAL_DIR / "dataset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_case(graph: Any, case: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    state = graph.invoke(
        {"request_id": uuid.uuid4().hex, "message": case["message"], "history": [], "llm_calls": 0, "timings_ms": {}}
    )
    guardrail, tool_call = state.get("guardrail"), state.get("tool_call")
    return {
        "id": case["id"],
        "route": state["route"],
        "guardrail": guardrail.motivo if guardrail else None,
        "camada": guardrail.camada if guardrail else None,
        "score": state.get("score"),
        "fallback": state.get("fallback", False),
        "tool": tool_call.name if tool_call else None,
        "tool_args": tool_call.args if tool_call else None,
        "urgent": state.get("urgent", False),
        "llm_calls": state.get("llm_calls", 0),
        "timings_ms": state.get("timings_ms", {}),
        "total_s": round(time.perf_counter() - start, 1),
        "reply": state["reply"],
    }


def _rate(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.0%})" if total else "—"


def compute_metrics(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    """Métricas da SPEC §7.3 e a lista de divergências (id: esperado × obtido)."""
    by_id = {r["id"]: r for r in results}
    pairs = [(c, by_id[c["id"]]) for c in cases if c["id"] in by_id]
    divergences: list[str] = []

    blocks = [(c, r) for c, r in pairs if c["expected_route"] == "BLOQUEIO"]
    allowed = [(c, r) for c, r in pairs if c["expected_route"] != "BLOQUEIO"]
    blocked_ok = sum(r["route"] == "BLOQUEIO" for _, r in blocks)
    reason_ok = sum(r["guardrail"] == c["expected_guardrail"] for c, r in blocks)
    false_pos = sum(r["route"] == "BLOQUEIO" for _, r in allowed)
    choice_ok = sum(r["route"] == c["expected_route"] for c, r in allowed)
    urgent = [(c, r) for c, r in allowed if c["urgent"]]
    urgent_ok = sum(r["route"] == "ATENDIMENTO_HUMANO" for _, r in urgent)
    covered = [(c, r) for c, r in pairs if c["expected_route"] == "CONSULTA_RAG" and c["expected_fallback"] is False]
    uncovered = [(c, r) for c, r in pairs if c["expected_route"] == "CONSULTA_RAG" and c["expected_fallback"] is True]
    covered_ok = sum(r["route"] == "CONSULTA_RAG" and not r["fallback"] for _, r in covered)
    uncovered_ok = sum(r["route"] == "CONSULTA_RAG" and r["fallback"] for _, r in uncovered)
    tools = [(c, r) for c, r in pairs if c["expected_route"] in {"AGENDAMENTO", "ATENDIMENTO_HUMANO"}]
    tool_ok = sum(r["tool"] == c["expected_tool"] for c, r in tools)
    rag_runs = [r for _, r in pairs if r["route"] == "CONSULTA_RAG"]

    for c, r in pairs:
        problems = []
        if r["route"] != c["expected_route"]:
            problems.append(f"rota {r['route']} (esperado {c['expected_route']})")
        if c["expected_route"] == "BLOQUEIO" and r["guardrail"] != c["expected_guardrail"]:
            problems.append(f"motivo {r['guardrail']} (esperado {c['expected_guardrail']})")
        if c["expected_fallback"] is not None and r["route"] == "CONSULTA_RAG" and r["fallback"] != c["expected_fallback"]:
            problems.append(f"fallback {r['fallback']} com score {r['score']} (esperado {c['expected_fallback']})")
        if c["expected_route"] in {"AGENDAMENTO", "ATENDIMENTO_HUMANO"} and r["tool"] != c["expected_tool"]:
            problems.append(f"tool {r['tool']} (esperado {c['expected_tool']})")
        if problems:
            divergences.append(f"{c['id']}: {'; '.join(problems)} | {c['message']}")

    calls_by_route: dict[str, list[int]] = defaultdict(list)
    for _, r in pairs:
        calls_by_route[r["route"]].append(r["llm_calls"])
    node_times: dict[str, list[float]] = defaultdict(list)
    for _, r in pairs:
        for node, ms in r["timings_ms"].items():
            node_times[node].append(ms / 1000)

    metrics = {
        "Noul: bloqueios corretos": _rate(blocked_ok, len(blocks)),
        "Noul: motivo correto": _rate(reason_ok, len(blocks)),
        "Noul: falsos positivos": _rate(false_pos, len(allowed)),
        "Choice: acurácia (meta ≥ 85%)": _rate(choice_ok, len(allowed)),
        "Recall de urgência (meta 100%)": _rate(urgent_ok, len(urgent)),
        "RAG coberto respondido (AC-RF02-11)": _rate(covered_ok, len(covered)),
        "RAG não coberto → fallback (AC-RF02-12)": _rate(uncovered_ok, len(uncovered)),
        "Tool correta (AC-RF03)": _rate(tool_ok, len(tools)),
        "Taxa de fallback na rota RAG": _rate(sum(r["fallback"] for r in rag_runs), len(rag_runs)),
        "Tempo médio RAG com geração": (
            f"{statistics.mean(r['total_s'] for r in rag_runs if not r['fallback']):.1f} s"
            if any(not r["fallback"] for r in rag_runs) else "—"
        ),
        "Chamadas ao LLM por rota (média)": ", ".join(
            f"{route} {statistics.mean(v):.1f}" for route, v in sorted(calls_by_route.items())
        ),
        "Latência média por nó": ", ".join(
            f"{node} {statistics.mean(v):.1f} s" for node, v in sorted(node_times.items()) if statistics.mean(v) >= 0.05
        ),
    }
    return metrics, divergences


def to_markdown(metrics: dict[str, str]) -> str:
    rows = "\n".join(f"| {name} | {value} |" for name, value in metrics.items())
    return f"| Métrica | Resultado |\n| :--- | :--- |\n{rows}"


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.graph import build_graph
    from app.main import build_deps

    parser = argparse.ArgumentParser(description="Avaliação do assistente com LLM real.")
    parser.add_argument("--only", help="ids separados por vírgula")
    parser.add_argument("--dataset", type=Path, default=DATASET, help="arquivo .jsonl (padrão: dataset.jsonl)")
    parser.add_argument("--label", default="eval")
    args = parser.parse_args(argv)

    cases = load_dataset(args.dataset)
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    settings = get_settings()
    graph = build_graph(build_deps(settings))
    results = []
    for i, case in enumerate(cases, start=1):
        result = run_case(graph, case)
        results.append(result)
        print(f"[{i:02d}/{len(cases)}] {case['id']:<7} {result['route']:<18} {result['total_s']:6.1f}s", flush=True)

    metrics, divergences = compute_metrics(cases, results)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.label}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(
        json.dumps(
            {"label": args.label, "model": settings.llm_model, "top_k": settings.top_k,
             "metrics": metrics, "divergences": divergences, "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nModelo: {settings.llm_model} · top_k={settings.top_k} · {len(cases)} casos\n")
    print(to_markdown(metrics))
    print("\nDivergências:" if divergences else "\nSem divergências.")
    for d in divergences:
        print(f"- {d}")
    print(f"\nResultados: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
