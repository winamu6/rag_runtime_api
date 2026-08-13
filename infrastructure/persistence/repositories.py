import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.persistence.models import (
    AgentRun,
    OutboxMessageModel,
    RawRLTransitionModel,
)
from shared_contracts.events import BaseEvent, OutboxMessage
from shared_contracts.policy import RawRLTransition, RewardStatus

logger = logging.getLogger(__name__)


class RunRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, run_id: UUID) -> Optional[AgentRun]:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_completed(
        self, run_id: UUID, final_answer: str, completed_at: datetime
    ) -> None:
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="COMPLETED",
                final_answer=final_answer,
                completed_at=completed_at,
            )
        )
        await self._session.execute(stmt)


class TransitionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_transitions(self, transitions: List[RawRLTransition]) -> None:
        models = [
            RawRLTransitionModel(
                id=t.id,
                run_id=t.run_id,
                trajectory_id=t.trajectory_id,
                decision_id=t.decision_id,
                hierarchy_level=t.hierarchy_level,
                state=t.state,
                action_index=t.action_index,
                action_name=t.action_name,
                next_state=t.next_state,
                done=t.done,
                next_action_mask=t.next_action_mask,
                reward_status=t.reward_status,
                reward_value=t.reward_value,
                observation_schema_version=t.observation_schema_version,
                action_space_version=t.action_space_version,
            )
            for t in transitions
        ]
        self._session.add_all(models)


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_event(
        self, event: BaseEvent, aggregate_id: UUID
    ) -> OutboxMessageModel:
        """Добавление события в Outbox при транзакции (используется в RuntimeChain)."""
        message = OutboxMessageModel(
            id=uuid4(),
            event_id=getattr(event, "event_id", uuid4()),
            event_type=event.event_type,
            aggregate_id=aggregate_id,
            payload=event.model_dump(mode="json"),
            status="PENDING",
            created_at=event.occurred_at,
        )
        self._session.add(message)
        return message

    async def fetch_pending_messages(
        self, batch_size: int = 50
    ) -> List[OutboxMessage]:
        """
        Забирает записи со статусом PENDING с применением FOR UPDATE SKIP LOCKED
        для фонового воркера OutboxProcessor.
        """
        stmt = (
            select(OutboxMessageModel)
            .where(OutboxMessageModel.status == "PENDING")
            .order_by(OutboxMessageModel.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            OutboxMessage(
                id=m.id,
                event_id=getattr(m, "event_id", m.id),
                event_type=m.event_type,
                aggregate_id=m.aggregate_id,
                payload=m.payload,
                status=m.status,
                created_at=m.created_at,
                processed_at=m.processed_at,
                retry_count=m.retry_count,
                error=m.error,
            )
            for m in models
        ]

    async def mark_as_processed(self, message_ids: List[UUID]) -> None:
        """Помечает список сообщений как успешно отправленные."""
        stmt = (
            update(OutboxMessageModel)
            .where(OutboxMessageModel.id.in_(message_ids))
            .values(
                status="PROCESSED",
                processed_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)

    async def mark_as_failed(
        self,
        message_id: UUID,
        error_reason: str,
        retry_count: int,
        max_retries: int = 5,
    ) -> None:
        """
        Обновляет запись при ошибке отправки.
        Если превышен лимит повторов, переводит статус в FAILED.
        """
        new_status = "FAILED" if retry_count >= max_retries else "PENDING"
        stmt = (
            update(OutboxMessageModel)
            .where(OutboxMessageModel.id == message_id)
            .values(
                status=new_status,
                retry_count=retry_count,
                error=error_reason,
            )
        )
        await self._session.execute(stmt)


class RewardRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def fetch_pending_transitions(self, run_id: UUID) -> List[RawRLTransition]:
        """Выбирает переходы прогона со статусом PENDING."""
        stmt = (
            select(RawRLTransitionModel)
            .where(
                RawRLTransitionModel.run_id == run_id,
                RawRLTransitionModel.reward_status == RewardStatus.PENDING,
            )
            .order_by(RawRLTransitionModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            RawRLTransition(
                id=m.id,
                run_id=m.run_id,
                trajectory_id=m.trajectory_id,
                decision_id=m.decision_id,
                hierarchy_level=m.hierarchy_level,
                state=m.state,
                action_index=m.action_index,
                action_name=m.action_name,
                next_state=m.next_state,
                done=m.done,
                next_action_mask=m.next_action_mask,
                reward_status=m.reward_status,
                reward_value=m.reward_value,
                observation_schema_version=m.observation_schema_version,
                action_space_version=m.action_space_version,
            )
            for m in models
        ]

    async def update_transition_rewards(
        self, transition_rewards: Dict[UUID, float]
    ) -> None:
        """Пакетное обновление статусов и значений наград."""
        for trans_id, reward_val in transition_rewards.items():
            stmt = (
                update(RawRLTransitionModel)
                .where(RawRLTransitionModel.id == trans_id)
                .values(
                    reward_status=RewardStatus.CALCULATED,
                    reward_value=reward_val,
                )
            )
            await self._session.execute(stmt)