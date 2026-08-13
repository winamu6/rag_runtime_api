import json
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Локальные импорты проекта
from infrastructure.database import get_db
from infrastructure.persistence.models import AgentRun, OutboxMessageModel, RunStatus
from presentation.api.schemas import RunResponse, CreateRunRequest, PaginatedRunsResponse, CancelRunResponse
from shared_contracts.policy import HierarchyLevel

router = APIRouter(prefix="/api/v1/runs", tags=["Runs API"])


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить выполнение задачи (Create Run)",
)
async def create_run(
    request: CreateRunRequest,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    now = datetime.now(timezone.utc)
    run_id = uuid4()

    # 1. Создаем объект AgentRun
    new_run = AgentRun(
        id=run_id,
        user_id=request.user_id,
        prompt=request.prompt,
        status=RunStatus.PENDING.value,
        run_metadata=request.metadata,
        created_at=now,
        updated_at=now,
    )

    # 2. Создаем событие в Transactional Outbox (в той же транзакции)
    outbox_event = OutboxMessageModel(
        id=uuid4(),
        aggregate_id=run_id,
        event_type="RUN_CREATED",
        payload={
            "run_id": str(run_id),
            "user_id": str(request.user_id),
            "prompt": request.prompt,
            "metadata": request.metadata,
            "created_at": now.isoformat(),
        },
        status="PENDING",
        created_at=now,
    )

    db.add(new_run)
    db.add(outbox_event)

    # Фиксируем транзакцию (атомарное сохранение в БД)
    await db.commit()
    await db.refresh(new_run)

    return RunResponse.model_validate(new_run)


@router.get(
    "",
    response_model=PaginatedRunsResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить список запусков (Runs)",
    description="Возвращает список запусков с фильтрацией по статусу и постраничной навигацией.",
)
async def list_runs(
    status_filter: Optional[RunStatus] = Query(
        default=None,
        alias="status",
        description="Фильтр по статусу выполнения задачи"
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Количество записей на страницу (от 1 до 100)"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Смещение от начала списка"
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedRunsResponse:
    query = select(AgentRun)
    count_query = select(func.count()).select_from(AgentRun)

    if status_filter is not None:
        query = query.where(AgentRun.status == status_filter.value)
        count_query = count_query.where(AgentRun.status == status_filter.value)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        query
        .order_by(AgentRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    runs = result.scalars().all()

    return PaginatedRunsResponse(
        items=[RunResponse.model_validate(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Получить текущий статус Run",
)
async def get_run_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запуск с id {run_id} не найден",
        )

    return RunResponse.model_validate(run)


@router.post(
    "/{run_id}/cancel",
    response_model=CancelRunResponse,
    summary="Отменить выполнение Run",
)
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CancelRunResponse:
    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запуск с id {run_id} не найден",
        )

    if run.status in [RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Невозможно отменить запуск в статусе {run.status}",
        )

    now = datetime.now(timezone.utc)
    run.status = RunStatus.CANCELLED.value
    run.updated_at = now

    outbox_event = OutboxMessageModel(
        id=uuid4(),
        aggregate_id=run_id,
        event_type="RUN_CANCELLED",
        payload={
            "run_id": str(run_id),
            "cancelled_at": now.isoformat(),
        },
        status="PENDING",
        created_at=now,
    )

    db.add(outbox_event)
    await db.commit()

    return CancelRunResponse(
        run_id=run.id,
        status=RunStatus.CANCELLED,
        cancelled_at=now,
    )


@router.get(
    "/{run_id}/stream",
    response_class=StreamingResponse,
    summary="SSE Стриминг выполнения шагов Run",
)
async def stream_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # Проверяем существование записи перед стартом стрима
    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запуск с id {run_id} не найден",
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            start_payload = {"run_id": str(run_id), "status": RunStatus.RUNNING.value}
            yield f"event: run_started\ndata: {json.dumps(start_payload, ensure_ascii=False)}\n\n"

            step_data = {
                "run_id": str(run_id),
                "hierarchy_level": HierarchyLevel.HIGH.value,
                "step_index": 1,
                "selected_action": "REASONING",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"event: step_executed\ndata: {json.dumps(step_data, ensure_ascii=False)}\n\n"

            completed_data = {
                "run_id": str(run_id),
                "status": RunStatus.COMPLETED.value,
                "final_answer": run.final_answer or "Финальный ответ агента.",
            }
            yield f"event: run_completed\ndata: {json.dumps(completed_data, ensure_ascii=False)}\n\n"

        except Exception as err:
            error_data = {
                "run_id": str(run_id),
                "status": RunStatus.FAILED.value,
                "error": str(err),
            }
            yield f"event: run_failed\ndata: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )