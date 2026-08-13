from uuid import uuid4
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("setup_database")]


async def test_submit_human_feedback_success(client: AsyncClient):
    create_run_res = await client.post(
        "/api/v1/runs",
        json={
            "user_id": str(uuid4()),
            "prompt": "Test prompt for feedback",
        },
    )
    assert create_run_res.status_code == 202
    run_id = create_run_res.json()["id"]

    payload = {
        "run_id": run_id,
        "target_type": "run",
        "target_id": run_id,
        "evaluator_id": "user_42",
        "score": 1.0,
        "feedback_type": "EXPERT",
        "comment": "Отличный результат",
    }

    response = await client.post(f"/api/v1/runs/{run_id}/feedback", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] == "ACCEPTED"