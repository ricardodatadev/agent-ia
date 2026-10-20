"""Dataset de avaliação (SPEC §7.3) e cálculo das métricas, sem LLM."""

from collections import Counter

from tests.eval.run_eval import compute_metrics, load_dataset

ROUTES = {"BLOQUEIO", "CONSULTA_RAG", "AGENDAMENTO", "ATENDIMENTO_HUMANO", "FORA_DO_NICHO"}
FIELDS = {"id", "message", "expected_route", "expected_guardrail", "expected_fallback", "expected_tool", "urgent", "notes"}


def test_dataset_tem_50_casos_validos_com_ids_unicos() -> None:
    cases = load_dataset()
    assert len(cases) == 50
    assert len({c["id"] for c in cases}) == 50
    assert all(set(c) == FIELDS and c["expected_route"] in ROUTES for c in cases)


def test_dataset_cobre_as_quantidades_minimas_da_spec() -> None:
    cases = load_dataset()
    routes = Counter(c["expected_route"] for c in cases)
    guardrails = Counter(c["expected_guardrail"] for c in cases)
    covered = sum(c["expected_route"] == "CONSULTA_RAG" and c["expected_fallback"] is False for c in cases)
    uncovered = sum(c["expected_route"] == "CONSULTA_RAG" and c["expected_fallback"] is True for c in cases)
    assert covered >= 10 and uncovered >= 4
    assert routes["AGENDAMENTO"] >= 6 and routes["FORA_DO_NICHO"] >= 4
    assert sum(c["urgent"] for c in cases) >= 6
    assert guardrails["OFENSA"] >= 4 and guardrails["PII"] >= 6


def _result(case: dict, **overrides: object) -> dict:
    base = {
        "id": case["id"], "route": case["expected_route"], "guardrail": case["expected_guardrail"],
        "score": 5, "fallback": bool(case["expected_fallback"]), "tool": case["expected_tool"],
        "llm_calls": 1, "timings_ms": {"noul": 1000.0}, "total_s": 1.0,
    }
    return {**base, **overrides}


def test_resultados_perfeitos_nao_tem_divergencias() -> None:
    cases = load_dataset()
    metrics, divergences = compute_metrics(cases, [_result(c) for c in cases])
    assert divergences == []
    assert metrics["Choice: acurácia (meta ≥ 85%)"] == "39/39 (100%)"
    assert metrics["Recall de urgência (meta 100%)"] == "7/7 (100%)"


def test_urgencia_bloqueada_conta_como_falha_de_recall_e_falso_positivo() -> None:
    cases = load_dataset()
    results = [_result(c, route="BLOQUEIO", guardrail="OFENSA") if c["id"] == "urg-03" else _result(c) for c in cases]
    metrics, divergences = compute_metrics(cases, results)
    assert metrics["Recall de urgência (meta 100%)"] == "6/7 (86%)"
    assert metrics["Noul: falsos positivos"] == "1/39 (3%)"
    assert any(d.startswith("urg-03: rota BLOQUEIO") for d in divergences)
