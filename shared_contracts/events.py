from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    """Типы доменных и системных событий в шине / outbox."""
    RUN_STARTED = "run.started"
    STEP_EXECUTED = "step.executed"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"
    FEEDBACK_RECEIVED = "feedback.received"
    REWARD_CALCULATED = "reward.calculated"


class BaseEvent(BaseModel):
    """Базовый класс для всех событий системы."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: UUID = Field(default_factory=uuid4, description="Уникальный идентификатор события")
    event_type: EventType = Field(..., description="Тип события")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время возникновения события в UTC",
    )


class RunStartedEvent(BaseEvent):
    """Событие запуска прогона (Run)."""
    event_type: EventType = Field(default=EventType.RUN_STARTED, frozen=True)
    run_id: UUID
    user_id: UUID
    prompt: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StepExecutedEvent(BaseEvent):
    """Событие выполнения отдельного шага политики/инструмента."""
    event_type: EventType = Field(default=EventType.STEP_EXECUTED, frozen=True)
    run_id: UUID
    trajectory_id: UUID
    step_index: int
    hierarchy_level: str
    decision_id: UUID
    action_name: str
    observation_schema_version: str
    action_space_version: str


class ExecutionCompletedEvent(BaseEvent):
    """Событие успешного завершения прогона."""
    event_type: EventType = Field(default=EventType.EXECUTION_COMPLETED, frozen=True)
    run_id: UUID
    trajectory_id: UUID
    total_steps: int
    final_answer: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionFailedEvent(BaseEvent):
    """Событие падения прогона с ошибкой."""
    event_type: EventType = Field(default=EventType.EXECUTION_FAILED, frozen=True)
    run_id: UUID
    trajectory_id: Optional[UUID] = None
    error_message: str
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionCancelledEvent(BaseEvent):
    """Событие отмены прогона пользователем."""
    event_type: EventType = Field(default=EventType.EXECUTION_CANCELLED, frozen=True)
    run_id: UUID
    cancelled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutboxMessage(BaseModel):
    """Схема записи события в таблицу Transactional Outbox БД."""
    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    event_type: EventType
    aggregate_id: UUID = Field(..., description="UUID агрегата (обычно run_id)")
    payload: Dict[str, Any] = Field(..., description="Сериализованный JSON события")
    status: str = Field(default="PENDING", description="PENDING | PROCESSED | FAILED")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    retry_count: int = Field(default=0)
    error: Optional[str] = None