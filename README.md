Markdown

# RAG Runtime API & Q-Network Inference Service

Производственный сервис исполнения агентов RAG, инференса Q-сети RL и управления графом рассуждений с гарантией транзакционности событий.

## 🚀 Основные архитектурные особенности

- **Read-Only Q-Inference**: Выполнение инференса в режиме `torch.inference_mode()` исключительно по весам и манифесту без загрузки состояния оптимизатора или буфера повторов (**B-05**).
- **Atomic Pointer Swap**: Бесшовное фоновое обновление весов активных моделей без блокировок HTTP-запросов и без простоя сервиса.
- **Transactional Outbox (B-06)**: Гарантированная отправка событий завершения траекторий (`ExecutionCompletedEvent`) и назначения наград (`HumanRewardAssignedEvent`) в шину данных с семантикой *At-Least-Once*.
- **Human Feedback API (B-07)**: Разделение этапа выполнения (где награды помечаются как `PENDING`) и этапа оценки асессорами/пользователями.
- **Context Isolation & State Integrity (B-04/B-08)**: Строгая изоляция `AgentState` от сервисов, атомарная валидация источника документов (`EvidenceValidator`) и корректная инициализация системных промптов.

---

## 🛠️ Переменные окружения

| Переменная | Описание | Значение по умолчанию |
| :--- | :--- | :--- |
| `DATABASE_URL` | Строка подключения к PostgreSQL (asyncpg) | `postgresql+asyncpg://postgres:postgres@localhost:5432/rag_runtime` |
| `MODEL_REGISTRY_POLL_SECONDS` | Интервал опроса новых чекпоинтов в секундах | `10` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Интервал обработки неотправленных событий Outbox | `2.0` |
| `LOG_LEVEL` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## 💻 Локальный запуск

### 1. Требования
- Python 3.11+
- PostgreSQL

### 2. Установка зависимостей

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Применение миграций БД
```Bash
alembic upgrade head
```

4. Запуск сервиса
```Bash
python main.py
# или напрямую через uvicorn:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Swagger-документация доступна по адресу: http://localhost:8000/docs
🐳 Запуск через Docker
1. Сборка образа
```Bash
docker build -t rag-runtime-api:latest .
```

2. Запуск контейнера
```Bash
docker run -d \
  --name rag-runtime-api \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host.docker.internal:5432/rag_db" \
  rag-runtime-api:latest
```

📡 Подробное описание API Endpoints
1. Системные эндпоинты
GET /health

Проверка работоспособности сервиса, подключения к PostgreSQL и статуса загрузки весов Q-сети в память.

**Response (200 OK):**

```JSON

{
  "status": "ok",
  "database": "connected",
  "model_status": {
    "loaded": true,
    "version": "v1.2.0",
    "device": "cuda:0"
  }
}
```

2. Управление запусками агента (AgentRun)
**POST /api/v1/runs**

Инициализация и запуск новой траектории рассуждений RAG-агента.

*    Request Body:

```JSON
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "prompt": "Какая максимальная грузоподъемность у техники Darex?",
  "run_metadata": {
    "client_version": "1.4.0",
    "environment": "production"
  }
}
```
*    Response (202 Accepted):

```JSON
{
  "id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "PENDING",
  "prompt": "Какая максимальная грузоподъемность у техники Darex?",
  "run_metadata": {
    "client_version": "1.4.0",
    "environment": "production"
  },
  "created_at": "2026-08-12T23:55:19.674364Z"
}
```
**GET /api/v1/runs/{run_id}**

Получение текущего статуса, метаданных и итогового ответа конкретного запуска.

*    Path Parameters:
   
     * run_id (UUID): Идентификатор запуска.

*    Response (200 OK):

```JSON
{
  "id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "COMPLETED",
  "prompt": "Какая максимальная грузоподъемность у техники Darex?",
  "final_answer": "Максимальная грузоподъемность составляет...",
  "error_message": null,
  "run_metadata": {
    "client_version": "1.4.0",
    "environment": "production"
  },
  "created_at": "2026-08-12T23:55:19.674364Z",
  "updated_at": "2026-08-12T23:55:22.102451Z",
  "completed_at": "2026-08-12T23:55:22.101200Z"
}
```

* Response (404 Not Found):

```JSON
{
  "detail": "Run with ID c9bf9e57-1685-4c89-bafb-ff5af830be8a not found"
}
```

**GET /api/v1/runs/{run_id}/stream**

Server-Sent Events (SSE) эндпоинт для реального потокового получения сгенерированных токенов, intermediate-состояний графа рассуждений и действий Q-сети.

*    Header: Accept: text/event-stream

*    Stream Events:

     *    event: token — очередной сгенерированный токен ответа.

     *    event: transition — информация об обработанном шаге в графе/RL-переходе.

     *    event: complete — завершение генерации траектории.

Пример потока:

```HTTP

event: transition
data: {"step": 1, "action": "RETRIEVE_DOCS", "q_value": 0.87}

event: token
data: {"delta": "Максимальная"}

event: token
data: {"delta": " грузоподъемность"}

event: complete
data: {"status": "COMPLETED", "completed_at": "2026-08-12T23:55:22.101200Z"}
```

3. Обратная связь и RL (Human Feedback API)
**POST /api/v1/runs/{run_id}/feedback**

Присвоение человеческой оценки (Human Reward) пройденной траектории рассуждения. Метод создает событие HumanRewardAssignedEvent в Transactional Outbox для последующего обучения Q-сети.

*    Path Parameters:

     *    run_id (UUID): Идентификатор запуска, к которому привязывается оценка.

*    Request Body:

```JSON
{
  "reward": 1.0,
  "assessor_id": "a1b2c3d4-e5f6-7890-abcd-1234567890ab",
  "comment": "Ответ точный, документы притянуты верно"
}
```

* Response (200 OK):

```JSON
{
  "status": "success",
  "run_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "reward": 1.0,
  "assigned_at": "2026-08-12T23:58:01.120493Z"
}
```
* Errors:
  * 400 Bad Request: Запуск еще не завершен (status != COMPLETED) или обратная связь уже была отправлена.
  * 404 Not Found: Запуск с таким run_id не найден.