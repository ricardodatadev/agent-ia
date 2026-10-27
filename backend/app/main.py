"""API FastAPI: POST /chat e GET /health (SPEC §5.3), com logs JSON e erros 503 amigáveis (RNF05, RNF06)."""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import DependencyUnavailable
from app.graph import GraphDeps, build_graph, to_sources
from app.guardrails import find_pii
from app.jev import JevJudge, JevQuestions, classify_jev_error, resolve_engine
from app.judge import Judge, LLMJudge
from app.llm import LLM_ERRORS, classify_llm_error, make_chat_model, make_judge_model, warm_up
from app.models import ChatRequest, ChatResponse, GraphState, RetrievedChunk
from app.rag import VectorStore

logger = logging.getLogger("app")

UNAVAILABLE_DETAIL = "Serviço temporariamente indisponível. Tente novamente em instantes."
CONFIG_ERROR_DETAIL = "Erro de configuração do assistente. Avise o responsável pelo serviço."
HEALTH_TIMEOUT_S = 5

# --------------------------------------------------------------------------- logs


class JsonFormatter(logging.Formatter):
    """Uma linha JSON por evento; campos de `extra` viram chaves do objeto."""

    _STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in self._STANDARD})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)  # stack só no log, nunca na resposta
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore"):  # registram URLs a cada chamada
        logging.getLogger(noisy).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- dependências


def build_judge(settings: Settings) -> Judge:
    """Motor das decisões (RF06): Jev da TypeSafe AI ou modo local. As perguntas do Jev são validadas sempre."""
    questions = JevQuestions.load()
    engine = resolve_engine(settings)
    if engine == "typesafe":
        judge: Judge = JevJudge.from_settings(settings, questions)
        model = settings.typesafe_model
    else:
        judge = LLMJudge(make_judge_model(settings))
        model = settings.llm_model
    reason = "JEV_PROVIDER" if settings.jev_provider != "auto" else (
        "auto: TYPESAFE_API_KEY definida" if engine == "typesafe" else "auto: sem TYPESAFE_API_KEY"
    )
    logger.info("decision_engine_selected", extra={"engine": engine, "model": model, "reason": reason})
    return judge


def build_deps(settings: Settings) -> GraphDeps:
    return GraphDeps(
        retriever=VectorStore.from_settings(settings),
        chat_model=make_chat_model(settings),
        judge=build_judge(settings),
        top_k=settings.top_k,
        score_threshold=settings.score_threshold,
        handoff_live=settings.handoff_live,
    )


HealthProbe = Callable[[], dict[str, Any]]


def make_health_probe(settings: Settings, store: VectorStore) -> HealthProbe:
    def probe() -> dict[str, Any]:
        status: dict[str, Any] = {"qdrant": "ok", "ollama": "ok", "collection_points": None}
        try:
            status["collection_points"] = store.count()
        except DependencyUnavailable:
            status["qdrant"] = "erro"
        try:
            httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=HEALTH_TIMEOUT_S).raise_for_status()
        except httpx.HTTPError:
            status["ollama"] = "erro"
        return status

    return probe


def to_response(state: GraphState) -> ChatResponse:
    contexts = [] if state.get("fallback") else state.get("contexts", [])
    return ChatResponse(
        request_id=state["request_id"],
        reply=state["reply"],
        route=state["route"],
        guardrail=state.get("guardrail"),
        tool_call=state.get("tool_call"),
        score=state.get("score"),
        fallback=state.get("fallback", False),
        sources=to_sources(contexts),
    )


def request_log(state: GraphState, req: ChatRequest, total_ms: float) -> dict[str, Any]:
    """Metadados da requisição — nunca o texto das mensagens (LGPD, RNF03)."""
    guardrail = state.get("guardrail")
    tool_call = state.get("tool_call")
    return {
        "request_id": state["request_id"],
        "route": state.get("route"),
        "guardrail": guardrail.model_dump() if guardrail else None,
        "score": state.get("score"),
        "fallback": state.get("fallback", False),
        "tool": tool_call.name if tool_call else None,
        "llm_calls": state.get("llm_calls", 0),
        "timings_ms": state.get("timings_ms", {}),
        "total_ms": total_ms,
        "message_len": len(req.message),
        "history_len": len(req.history),
    }


def startup_ingest(store: VectorStore) -> None:
    """Ingere os documentos só se a coleção estiver vazia; falha vai para o log, não derruba a API."""
    try:
        report = store.ensure_ingested()
    except Exception as exc:  # noqa: BLE001 — a API sobe mesmo sem ingestão (o /health mostra o problema)
        logger.error("startup_ingest_failed", extra={"error": type(exc).__name__})
        return
    if report is None:
        logger.info("startup_ingest_skipped", extra={"reason": "coleção já populada"})
    else:
        logger.info("startup_ingest_done", extra={"files": report.files, "chunks": report.chunks, "skipped": report.skipped})


def startup_warm_up(settings: Settings, deps: GraphDeps) -> None:
    """Carrega os modelos e processa uma vez os prompts das decisões (o Ollama reaproveita o prefixo em cache).

    Sem isso, a 1ª pergunta após subir levava ~3 min em CPU (cada prompt de sistema ~30 s na 1ª vez).
    """
    start = time.perf_counter()
    sample = RetrievedChunk(source="aquecimento", chunk_index=0, text="A UBS funciona de segunda a sexta.")
    try:
        warm_up(settings)
        # Só o modo local com Ollama tem carga a frio; com Jev ou API, aquecer só gastaria tokens.
        if settings.llm_provider == "ollama" and isinstance(deps.judge, LLMJudge):
            deps.judge.noul("Olá")
            deps.judge.choice("Olá", [])
            deps.judge.score("Olá", [sample])
    except LLM_ERRORS as exc:  # sobe mesmo assim; a 1ª pergunta só fica mais lenta
        logger.warning("startup_warmup_failed", extra={"model": settings.llm_model, "error": type(exc).__name__})
        return
    logger.info("startup_warmup_done", extra={"model": settings.llm_model, "ms": round((time.perf_counter() - start) * 1000)})


# --------------------------------------------------------------------------- app


def create_app(
    settings: Settings | None = None,
    deps: GraphDeps | None = None,
    health_probe: HealthProbe | None = None,
) -> FastAPI:
    """`deps` e `health_probe` permitem injetar dublês nos testes."""
    configure_logging()
    settings = settings or get_settings()
    real_llm = deps is None  # dublês de teste não aquecem nada
    if deps is None:
        deps = build_deps(settings)
        if health_probe is None and isinstance(deps.retriever, VectorStore):
            health_probe = make_health_probe(settings, deps.retriever)
    graph = build_graph(deps)
    store = deps.retriever if isinstance(deps.retriever, VectorStore) else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.auto_ingest and store is not None:
            startup_ingest(store)
        if real_llm:
            startup_warm_up(settings, deps)
        yield
        if isinstance(deps.judge, JevJudge):  # fecha o cliente HTTP do SDK
            deps.judge.close()

    app = FastAPI(title="Assistente UBS · Agente de IA", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> JSONResponse:
        status = health_probe() if health_probe else {}
        ok = all(v != "erro" for v in status.values())
        return JSONResponse({"status": "ok" if ok else "degradado", **status}, status_code=200 if ok else 503)

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse | JSONResponse:
        request_id = uuid.uuid4().hex
        # O Noul avalia só a mensagem atual: turnos antigos com PII (regex) não seguem para os LLMs.
        history = [t for t in req.history if not find_pii(t.content)]
        state: GraphState = {
            "request_id": request_id,
            "message": req.message,
            "history": history,
            "llm_calls": 0,
            "timings_ms": {},
        }
        start = time.perf_counter()
        try:
            final = graph.invoke(state)
        except Exception as exc:
            jev_kind = classify_jev_error(exc)
            kind = "unavailable" if isinstance(exc, DependencyUnavailable) else (jev_kind or classify_llm_error(exc))
            if kind is None:
                raise
            dependency = exc.dependency if isinstance(exc, DependencyUnavailable) else ("jev" if jev_kind else "llm")
            event = "dependency_error" if kind == "unavailable" else "llm_config_error"
            logger.error(
                event,
                exc_info=True,
                extra={"request_id": request_id, "dependency": dependency, "error": type(exc).__name__},
            )
            if kind == "config":
                return JSONResponse({"detail": CONFIG_ERROR_DETAIL}, status_code=500)
            return JSONResponse({"detail": UNAVAILABLE_DETAIL}, status_code=503)
        total_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info("chat_request", extra=request_log(final, req, total_ms))
        return to_response(final)

    return app


app = create_app()
