from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from presentation.api.schemas import FeedbackResponse, ActionFeedbackPayload, EvidenceFeedbackPayload, \
    CorrectionFeedbackPayload

from shared_contracts.events import EventType
from shared_contracts.feedback import (
    FeedbackTargetType,
    HumanFeedbackRequest,
)
from infrastructure.persistence.unit_of_work import SQLAlchemyAsyncUnitOfWork

router = APIRouter(prefix="/api/v1/runs", tags=["Feedback API"])


async def get_uow() -> SQLAlchemyAsyncUnitOfWork:
    raise NotImplementedError("Dependency get_uow must be overridden in FastAPI app initialization.")


@router.post(
    "/{run_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Общий отзыв по результатам выполнения Run",
)
async def submit_general_feedback(
    run_id: UUID,
    request: HumanFeedbackRequest,
    uow: SQLAlchemyAsyncUnitOfWork = Depends(get_uow),
) -> FeedbackResponse:
    """
    Принимает базовую человеческую оценку (бинарный/скалярный score и комментарий)
    для всей траектории Run или конкретного таргета и сохраняет Outbox-событие.
    """
    feedback_id = uuid4()
    now = datetime.now(timezone.utc)
    request.run_id = run_id

    async with uow.transaction():
        run = await uow.runs.get_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        await uow.outbox.add_event(
            event_type=EventType.FEEDBACK_RECEIVED,
            aggregate_id=run_id,
            payload={
                "feedback_id": str(feedback_id),
                "run_id": str(run_id),
                "target_type": request.target_type.value if hasattr(request.target_type, 'value') else str(request.target_type),
                "target_id": str(request.target_id) if request.target_id else None,
                "score": request.score,
                "comment": request.comment,
            },
        )

    return FeedbackResponse(
        feedback_id=feedback_id,
        run_id=run_id,
        target_type=request.target_type,
        target_id=request.target_id,
        status="ACCEPTED",
        received_at=now,
    )


@router.post(
    "/{run_id}/feedback/action",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Отзыв на конкретное действие политики (Action level)",
)
async def submit_action_feedback(
    run_id: UUID,
    payload: ActionFeedbackPayload,
    uow: SQLAlchemyAsyncUnitOfWork = Depends(get_uow),
) -> FeedbackResponse:
    """
    Фиксирует корректировку для конкретного шага принятия решения (Policy Decision).
    """
    feedback_id = uuid4()
    now = datetime.now(timezone.utc)

    async with uow.transaction():
        run = await uow.runs.get_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        await uow.outbox.add_event(
            event_type=EventType.FEEDBACK_RECEIVED,
            aggregate_id=run_id,
            payload={
                "feedback_id": str(feedback_id),
                "run_id": str(run_id),
                "target_type": FeedbackTargetType.ACTION.value,
                "target_id": str(payload.decision_id),
                "preferred_action": payload.preferred_action,
                "rejected_action": payload.rejected_action,
                "comment": payload.comment,
            },
        )

    return FeedbackResponse(
        feedback_id=feedback_id,
        run_id=run_id,
        target_type=FeedbackTargetType.ACTION,
        target_id=payload.decision_id,
        status="ACCEPTED",
        received_at=now,
    )


@router.post(
    "/{run_id}/feedback/evidence",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Оценка релевантности найденных доказательств (Evidence Level)",
)
async def submit_evidence_feedback(
    run_id: UUID,
    payload: EvidenceFeedbackPayload,
    uow: SQLAlchemyAsyncUnitOfWork = Depends(get_uow),
) -> FeedbackResponse:
    """
    Принимает оценку качества извлеченного контекста / найденных фрагментов текста.
    """
    feedback_id = uuid4()
    now = datetime.now(timezone.utc)

    async with uow.transaction():
        run = await uow.runs.get_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        await uow.outbox.add_event(
            event_type=EventType.FEEDBACK_RECEIVED,
            aggregate_id=run_id,
            payload={
                "feedback_id": str(feedback_id),
                "run_id": str(run_id),
                "target_type": FeedbackTargetType.EVIDENCE.value,
                "target_id": str(payload.evidence_id),
                "score": payload.score,
                "is_relevant": payload.is_relevant,
                "comment": payload.comment,
            },
        )

    return FeedbackResponse(
        feedback_id=feedback_id,
        run_id=run_id,
        target_type=FeedbackTargetType.EVIDENCE,
        target_id=payload.evidence_id,
        status="ACCEPTED",
        received_at=now,
    )


@router.post(
    "/{run_id}/feedback/correction",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Передача исправленного эталонного ответа (Correction / Golden Answer)",
)
async def submit_correction_feedback(
    run_id: UUID,
    payload: CorrectionFeedbackPayload,
    uow: SQLAlchemyAsyncUnitOfWork = Depends(get_uow),
) -> FeedbackResponse:
    """
    Принимает от человека идеальный ответ (Golden Answer).
    """
    feedback_id = uuid4()
    now = datetime.now(timezone.utc)

    async with uow.transaction():
        run = await uow.runs.get_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        await uow.outbox.add_event(
            event_type=EventType.FEEDBACK_RECEIVED,
            aggregate_id=run_id,
            payload={
                "feedback_id": str(feedback_id),
                "run_id": str(run_id),
                "target_type": FeedbackTargetType.RUN.value,
                "target_id": str(run_id),
                "corrected_answer": payload.corrected_answer,
                "comment": payload.comment,
            },
        )

    return FeedbackResponse(
        feedback_id=feedback_id,
        run_id=run_id,
        target_type=FeedbackTargetType.RUN,
        target_id=run_id,
        status="ACCEPTED",
        received_at=now,
    )