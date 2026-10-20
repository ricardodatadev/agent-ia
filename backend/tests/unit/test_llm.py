"""Provedor do LLM configurável (ADR-13), sem rede."""

import anthropic
import httpx
import pytest
from google.genai import errors as google_errors
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from app.config import Settings
from app.llm import LLMConfigError, classify_llm_error, make_chat_model, make_judge_model, message_text

REQ = httpx.Request("POST", "https://api.example.com")


def claude(**overrides: object) -> Settings:
    return Settings(llm_provider="anthropic", llm_model="claude-opus-5-5", anthropic_api_key="sk-ant-test", **overrides)


def gemini() -> Settings:
    return Settings(llm_provider="google", llm_model="gemini-2.5-flash", google_api_key="g-test")


def test_padrao_e_ollama_local_com_json_nas_decisoes() -> None:
    judge, chat = make_judge_model(Settings()), make_chat_model(Settings())
    assert isinstance(judge, ChatOllama) and isinstance(chat, ChatOllama)
    assert judge.model == "llama3.2:3b" and judge.format == "json" and judge.temperature == 0
    assert chat.format is None and chat.num_predict == 400


def test_claude_sem_temperature_com_effort_e_folga_de_tokens() -> None:
    model = make_judge_model(claude(anthropic_effort="low"))
    assert isinstance(model, ChatAnthropic)
    payload = model._get_request_payload([SystemMessage("sys"), HumanMessage("oi")])
    assert "temperature" not in payload
    assert payload["output_config"] == {"effort": "low"}
    assert payload["max_tokens"] == 1024 and payload["model"] == "claude-opus-5-5"


def test_claude_effort_vazio_nao_e_enviado() -> None:
    payload = make_chat_model(claude(anthropic_effort="")).\
        _get_request_payload([HumanMessage("oi")])
    assert "output_config" not in payload and payload["max_tokens"] == 2048


def test_gemini_pede_json_so_nas_decisoes() -> None:
    judge, chat = make_judge_model(gemini()), make_chat_model(gemini())
    assert isinstance(judge, ChatGoogleGenerativeAI)
    assert judge.response_mime_type == "application/json" and judge.temperature == 0
    assert chat.response_mime_type is None


@pytest.mark.parametrize(
    ("settings", "variable"),
    [
        (Settings(llm_provider="anthropic", llm_model="claude-opus-5-5"), "ANTHROPIC_API_KEY"),
        (Settings(llm_provider="google", llm_model="gemini-2.5-flash", google_api_key=""), "GOOGLE_API_KEY"),
    ],
)
def test_chave_ausente_falha_citando_a_variavel(settings: Settings, variable: str) -> None:
    with pytest.raises(LLMConfigError, match=variable):
        make_chat_model(settings)


def test_chave_nao_aparece_na_representacao() -> None:
    assert "sk-ant-test" not in repr(claude())


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (anthropic.RateLimitError("limite", response=httpx.Response(429, request=REQ), body=None), "unavailable"),
        (anthropic.InternalServerError("5xx", response=httpx.Response(500, request=REQ), body=None), "unavailable"),
        (anthropic.APITimeoutError(request=REQ), "unavailable"),
        (anthropic.AuthenticationError("chave", response=httpx.Response(401, request=REQ), body=None), "config"),
        (google_errors.ClientError(429, {"error": {"message": "quota"}}), "unavailable"),
        (google_errors.ClientError(403, {"error": {"message": "chave"}}), "config"),
        (google_errors.ServerError(503, {"error": {"message": "indisponível"}}), "unavailable"),
        (httpx.ConnectError("ollama fora"), "unavailable"),
        (LLMConfigError("sem chave"), "config"),
        (ValueError("bug"), None),
    ],
)
def test_mapeamento_de_erros(exc: BaseException, kind: str | None) -> None:
    assert classify_llm_error(exc) == kind


def test_texto_ignora_blocos_de_thinking() -> None:
    message = AIMessage(content=[{"type": "thinking", "thinking": "pensando..."}, {"type": "text", "text": "Resposta."}])
    assert message_text(message) == "Resposta."
