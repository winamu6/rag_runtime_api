FROM python:3.11-slim AS builder

WORKDIR /app

# Установка системных зависимостей для сборки пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Установка зависимостей с wheels
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim AS runner

WORKDIR /app

# Копирование установленных библиотек из этапа builder
COPY --from=builder /install /usr/local

# Копирование исходного кода приложения
COPY . /app/rag_runtime_api

# Настройка PYTHONPATH для корректного импорта модулей
ENV PYTHONPATH=/app/rag_runtime_api
ENV PYTHONUNBUFFERED=1

# Создание не-root пользователя для безопасности
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]