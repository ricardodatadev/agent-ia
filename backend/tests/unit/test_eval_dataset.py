"""Dataset de avaliação (SPEC §7.3) e cálculo das métricas, sem LLM."""

from collections import Counter

from app.guardrails import find_pii, urgency_signal
from tests.eval.run_eval import EVAL_DIR, compute_metrics, load_dataset

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


# --------------------------------------------------------------------------- dataset de robustez (T-26)

ROBUSTEZ = EVAL_DIR / "dataset_robustez.jsonl"


def test_dataset_de_robustez_e_valido() -> None:
    cases = load_dataset(ROBUSTEZ)
    assert len(cases) == 16 and len({c["id"] for c in cases}) == 16
    assert all(set(c) == FIELDS and c["expected_route"] in ROUTES for c in cases)
    groups = Counter(c["id"].split("-")[1] for c in cases)
    assert groups == {"urg": 7, "neg": 4, "pii": 5}


# O que a camada DETERMINÍSTICA faz com cada caso (sem LLM): é o que vale no plano B e no modo local.
RULE_URGENCY = {
    "rob-urg-01": "none", "rob-urg-02": "none", "rob-urg-03": "none", "rob-urg-04": "none", "rob-urg-05": "none",
    "rob-urg-06": "urgent", "rob-urg-07": "urgent",
    "rob-neg-01": "negated", "rob-neg-02": "negated",
    "rob-neg-03": "urgent", "rob-neg-04": "urgent",  # limitações conhecidas (fato antigo, pergunta informativa)
}
RULE_PII_REGEX = {"rob-pii-01", "rob-pii-02", "rob-pii-03", "rob-pii-04"}  # rob-pii-05 só a camada semântica


def test_dataset_de_saude_e_valido() -> None:  # RF07, T-28
    cases = load_dataset(EVAL_DIR / "dataset_saude.jsonl")
    assert len(cases) == 14 and len({c["id"] for c in cases}) == 14
    assert all(set(c) == FIELDS and c["expected_route"] in ROUTES for c in cases)
    groups = Counter(c["id"].split("-")[1] for c in cases)
    assert groups == {"inf": 7, "diag": 3, "rem": 2, "nao": 2}
    # Nenhum caso é decidido pela camada determinística: mede só o Choice, o Score e a geração.
    assert all(urgency_signal(c["message"]) == "none" and find_pii(c["message"]) is None for c in cases)


def test_dataset_da_rede_municipal_e_valido() -> None:  # RF08, T-30
    cases = load_dataset(EVAL_DIR / "dataset_rede.jsonl")
    assert len(cases) == 9 and len({c["id"] for c in cases}) == 9
    assert all(set(c) == FIELDS and c["expected_route"] == "CONSULTA_RAG" for c in cases)
    groups = Counter(c["id"].split("-")[1] for c in cases)
    assert groups == {"inf": 7, "amb": 1, "nao": 1}
    assert all(urgency_signal(c["message"]) == "none" and find_pii(c["message"]) is None for c in cases)


def test_camada_deterministica_no_dataset_de_robustez() -> None:
    for case in load_dataset(ROBUSTEZ):
        cid, message = case["id"], case["message"]
        if cid in RULE_URGENCY:
            assert urgency_signal(message) == RULE_URGENCY[cid], cid
        if cid.startswith("rob-pii"):
            assert (find_pii(message) is not None) == (cid in RULE_PII_REGEX), cid
