"""shared_contracts/model_registry.py

Контракты и статусы чекпоинтов моделей для Model Registry.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from shared_contracts.policy import HierarchyLevel


class CheckpointStatus(str, Enum):
    """Статусы жизненного цикла чекпоинта Q-сети в Model Registry."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class ModelCheckpointMetadata(BaseModel):
    """Метаданные чекпоинта модели для обмена между Model Registry и API/Learner."""

    checkpoint_id: UUID = Field(..., description="Уникальный идентификатор чекпоинта")
    hierarchy_level: HierarchyLevel = Field(..., description="Уровень иерархии Q-сети")
    status: CheckpointStatus = Field(..., description="Текущий статус чекпоинта")
    artifact_uri: str = Field(..., description="S3 / URI путь к файлу весов")
    artifact_sha256: str = Field(..., description="SHA256 контрольная сумма файла весов")
    observation_schema_version: str = Field(..., description="Версия схемы наблюдений")
    action_space_version: str = Field(..., description="Версия пространства действий")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания чекпоинта",
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Метрики обучения/валидации"
    )