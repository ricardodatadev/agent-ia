"""Erros de dependências externas (Qdrant, LLM, Jev) — viram 503 na API (RNF05)."""


class DependencyUnavailable(RuntimeError):
    """Uma dependência externa não respondeu (conexão, timeout, limite, 5xx)."""

    def __init__(self, dependency: str, detail: str = "") -> None:
        self.dependency = dependency
        super().__init__(f"{dependency} indisponível{': ' + detail if detail else ''}")
