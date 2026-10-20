"""API FastAPI: POST /chat e GET /health (SPEC §5.3)."""

import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import ChatRequest, ChatResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Assistente UBS · Agente de IA", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        # Stub (T-01): o grafo real entra na T-05.
        return ChatResponse(
            request_id=uuid.uuid4().hex,
            reply="Olá! Em breve vou responder suas dúvidas sobre a UBS.",
            route="CONSULTA_RAG",
        )

    return app


app = create_app()
