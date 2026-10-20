FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências em camada própria: só reinstala quando o requirements.txt muda.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY data/ data/
COPY jevs/ jevs/

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
