from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from shared_contracts.policy import RewardStatus


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionCompletedEvent(BaseModel):
    """Событие завершения работы агента над траекторией."""

    event_id: UUID = Field(..., description="Уникальный ID события")
    event_type: str = Field("EXECUTION_COMPLETED", description="Тип события")
    schema_version: int = Field(1, description="Версия схемы события")
    run_id: UUID = Field(..., description="ID запуска")
    trajectory_id: UUID = Field(..., description="ID траектории RL")
    final_answer: str = Field(..., description="Итоговый ответ агента")
    status: AgentStatus = Field(..., description="Статус завершения")
    policy_decision_ids: List[UUID] = Field(default_factory=list)
    reasoning_graph_id: UUID = Field(..., description="ID графа рассуждений")
    evidence_ids: List[UUID] = Field(default_factory=list)
    agent_result_ids: List[UUID] = Field(default_factory=list)
    transition_ids: List[UUID] = Field(default_factory=list)
    latency_ms: int = Field(..., description="Время выполнения в миллисекундах")
    prompt_tokens: int = Field(0, description="Использовано prompt токенов")
    completion_tokens: int = Field(0, description="Использовано completion токенов")
    runtime_error_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HumanRewardAssignedEvent(BaseModel):
    """Событие назначения награды человеком/асессором для траектории (B-07)."""

    event_id: UUID = Field(..., description="Уникальный ID события")
    event_type: str = Field("HUMAN_REWARD_ASSIGNED", description="Тип события")
    schema_version: int = Field(1, description="Версия схемы события")
    run_id: UUID = Field(..., description="ID запуска")
    trajectory_id: UUID = Field(..., description="ID RL траектории")
    evaluator_id: str = Field(..., description="Идентификатор оценитьеля (человека или системы)")
    reward_value: float = Field(..., ge=-1.0, le=1.0, description="Значение награды от -1.0 до 1.0")
    reward_status: RewardStatus = Field(RewardStatus.ASSIGNED, description="Статус награды")
    comment: Optional[str] = Field(None, description="Опциональный комментарий асессора")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))