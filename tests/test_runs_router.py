from uuid import uuid4
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("setup_database")]


async def test_create_run_success(client: AsyncClient):
    """Тест создания нового запуска (Create Run)."""
    payload = {
        "user_id": str(uuid4()),
        "prompt": "Проанализируй финансовую отчетность за Q3",
        "metadata": {"env": "test"},
    }

    response = await client.post("/api/v1/runs", json=payload)

    assert response.status_code == 202
    data = response.json()

    assert "id" in data
    assert data["user_id"] == payload["user_id"]
    assert data["status"] == "PENDING"


async def test_create_run_validation_error(client: AsyncClient):
    """Тест валидации: пустой prompt должен возвращать 422 Unprocessable Entity."""
    payload = {
        "user_id": str(uuid4()),
        "prompt": "",
    }

    response = await client.post("/api/v1/runs", json=payload)

    assert response.status_code == 422


async def test_get_run_status(client: AsyncClient):
    """Тест получения статуса конкретного Run."""
    # 1. Создаем Run
    create_res = await client.post(
        "/api/v1/runs",
        json={"user_id": str(uuid4()), "prompt": "Test prompt"},
    )
    run_id = create_res.json()["id"]

    response = await client.get(f"/api/v1/runs/{run_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id


async def test_cancel_run(client: AsyncClient):
    """Тест отмены выполнения задачи."""
    create_res = await client.post(
        "/api/v1/runs",
        json={"user_id": str(uuid4()), "prompt": "Test prompt"},
    )
    run_id = create_res.json()["id"]

    response = await client.post(f"/api/v1/runs/{run_id}/cancel")

    assert response.status_code == 200
    data = response.json()

    assert data.get("run_id") == run_id or data.get("id") == run_id
    assert data["status"] == "CANCELLED"


async def test_stream_run_sse(client: AsyncClient):
    """Тест SSE-стриминга шагов выполнения."""
    create_res = await client.post(
        "/api/v1/runs",
        json={"user_id": str(uuid4()), "prompt": "Test prompt"},
    )
    run_id = create_res.json()["id"]

    response = await client.get(f"/api/v1/runs/{run_id}/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]