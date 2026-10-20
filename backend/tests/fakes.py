"""Dublês de teste: embeddings determinísticos, sem Ollama."""

import hashlib
import math
import re
import unicodedata

from langchain_core.embeddings import Embeddings


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class FakeEmbeddings(Embeddings):
    """Bag-of-words com hashing: textos com palavras em comum ficam próximos no cosseno."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in re.findall(r"\w{3,}", _normalize(text)):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]
