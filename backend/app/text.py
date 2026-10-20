"""Normalização de texto para as comparações determinísticas (minúsculas, sem acentos)."""

import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    return re.findall(r"\w+", normalize(text))
