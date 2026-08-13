from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from infrastructure.database import Base
from shared_contracts.policy import HierarchyLevel, RewardStatus


class RunStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Уникальный идентификатор запуска",
    )
    user_id: Mapped[UUID] = mapped_column(
        index=True,
        nullable=False,
        comment="Идентификатор пользователя",
    )
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Исходный запрос пользователя",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=RunStatus.PENDING.value,
        index=True,
        nullable=False,
        comment="Текущий статус выполнения задачи",
    )
    run_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Метаданные запуска в формате JSON",
    )
    final_answer: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сгенерированный итоговый ответ агента",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Текст ошибки при сбое выполнения",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Дата и время создания записи (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Дата и время последнего обновления (UTC)",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время завершения (UTC)",
    )

    # Связь с RL-переходами (Transitions)
    transitions: Mapped[List["RawRLTransitionModel"]] = relationship(
        "RawRLTransitionModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class RawRLTransitionModel(Base):
    """Модель сырых RL-переходов для обучения и анализа траекторий."""

    __tablename__ = "raw_rl_transitions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trajectory_id: Mapped[UUID] = mapped_column(
        index=True,
        nullable=False,
        default=uuid4,
    )
    decision_id: Mapped[UUID] = mapped_column(
        nullable=False,
        default=uuid4,
    )
    hierarchy_level: Mapped[HierarchyLevel] = mapped_column(
        SQLEnum(HierarchyLevel, native_enum=False, length=10),
        nullable=False,
    )
    state: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    action_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    action_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    next_state: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    done: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    next_action_mask: Mapped[List[Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    reward_status: Mapped[RewardStatus] = mapped_column(
        SQLEnum(RewardStatus, native_enum=False, length=20),
        nullable=False,
        default=RewardStatus.PENDING,
    )
    reward_value: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )
    observation_schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    action_space_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Обратная связь с родителем AgentRun
    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="transitions")

    __table_args__ = (
        Index("idx_transitions_run_level", "run_id", "hierarchy_level"),
        Index("idx_transitions_reward_status", "reward_status"),
    )


class OutboxMessageModel(Base):
    """Модель для паттерна Transactional Outbox."""

    __tablename__ = "transactional_outbox"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Уникальный идентификатор сообщения outbox",
    )
    event_id: Mapped[UUID] = mapped_column(
        default=uuid4,
        nullable=False,
        comment="Идентификатор исходного события",
    )
    aggregate_id: Mapped[UUID] = mapped_column(
        index=True,
        nullable=False,
        comment="Идентификатор сущности (например, run_id)",
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="Тип события (например, RUN_CREATED)",
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Тело события в формате JSON",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        index=True,
        nullable=False,
        comment="Статус обработки: PENDING, PROCESSED, FAILED",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество попыток отправки",
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Текст последней ошибки при отправке",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Дата и время создания события (UTC)",
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время публикации в брокер (UTC)",
    )