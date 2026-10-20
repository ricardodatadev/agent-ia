"""Ingestão dos documentos da UBS no Qdrant (SPEC RF01).

Uso:
    python scripts/ingest.py [--data-dir backend/data]
    docker compose run --rm backend python scripts/ingest.py
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.errors import DependencyUnavailable  # noqa: E402
from app.rag import DATA_DIR, VectorStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingere os documentos da UBS no Qdrant.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = get_settings()
    store = VectorStore.from_settings(settings)
    try:
        report = store.ingest_dir(args.data_dir)
    except DependencyUnavailable as exc:
        target = settings.qdrant_url if exc.dependency == "qdrant" else settings.ollama_base_url
        print(f"ERRO: {exc.dependency} indisponível em {target}. Verifique se o serviço está no ar.", file=sys.stderr)
        return 1

    for name in report.skipped:
        print(f"AVISO: '{name}' ignorado (vazio ou formato não suportado).")
    print(
        f"Ingestão concluída: {report.files} arquivo(s), {report.chunks} chunk(s) "
        f"na coleção '{settings.qdrant_collection}' (total: {store.count()} pontos)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
