from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# 1. СИСТЕМНЫЕ СХЕМЫ (System & Health)
# =====================================================================

class ModelStatus(BaseModel):
    loaded: bool = Field(..., description="Флаг загрузки весов модели/Q-сети")
    version: str = Field(..., description="Версия модели")
    device: str = Field(..., description="Устройство выполнения (cpu/cuda)")


class HealthCheckResponse(BaseModel):
    status: str = Field("ok", description="Статус сервиса")
    database: str = Field("connected", description="Состояние подключения к БД")
    model_status: Optional[ModelStatus] = Field(None, description="Статус модели RL")


# =====================================================================
# 2. СХЕМЫ УПРАВЛЕНИЯ ЗАПУСКАМИ (Agent Runs API)
# =====================================================================

class CreateRunRequest(BaseModel):
    user_id: UUID = Field(..., description="Идентификатор пользователя")
    prompt: str = Field(..., min_length=1, description="Исходный запрос пользователя")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        alias="run_metadata",
        description="Произвольные метаданные клиента/окружения",
    )

    model_config = ConfigDict(populate_by_name=True)


class RunResponse(BaseModel):
    id: UUID = Field(..., description="Уникальный идентификатор запуска")
    user_id: UUID = Field(..., description="Идентификатор пользователя")
    prompt: str = Field(..., description="Исходный текст запроса")
    status: str = Field(..., description="Текущий статус (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)")
    final_answer: Optional[str] = Field(None, description="Итоговый сгенерированный ответ")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке, если запуск упал")
    run_metadata: Dict[str, Any] = Field(default_factory=dict, description="Метаданные запуска")
    created_at: datetime = Field(..., description="Время создания запуска")
    updated_at: datetime = Field(..., description="Время последнего обновления")
    completed_at: Optional[datetime] = Field(None, description="Время завершения выполнения")

    model_config = ConfigDict(from_attributes=True)


class PaginatedRunsResponse(BaseModel):
    items: List[RunResponse] = Field(..., description="Список запусков")
    total: int = Field(..., ge=0, description="Общее количество записей")
    limit: int = Field(..., ge=1, le=100, description="Размер страницы")
    offset: int = Field(..., ge=0, description="Смещение")


class CancelRunResponse(BaseModel):
    run_id: UUID = Field(..., description="ID отмененного запуска")
    status: str = Field("CANCELLED", description="Новый статус запуска")
    cancelled_at: datetime = Field(..., description="Время отмены")


# =====================================================================
# 3. СХЕМЫ ДЛЯ SSE СТРИМИНГА (Server-Sent Events)
# =====================================================================

class StreamRunStartedEvent(BaseModel):
    run_id: UUID
    status: str = "RUNNING"


class StreamStepExecutedEvent(BaseModel):
    run_id: UUID
    hierarchy_level: str = Field(..., description="Уровень иерархии политики (HIGH, LOW и т.д.)")
    step_index: int = Field(..., ge=1, description="Номер шага траектории")
    selected_action: str = Field(..., description="Выбранное действие агента")
    timestamp: datetime


class StreamRunCompletedEvent(BaseModel):
    run_id: UUID
    status: str = "COMPLETED"
    final_answer: str


class StreamRunFailedEvent(BaseModel):
    run_id: UUID
    status: str = "FAILED"
    error: str


# =====================================================================
# 4. СХЕМЫ ОБРАТНОЙ СВЯЗИ И RL (Feedback API)
# =====================================================================

class HumanFeedbackRequest(BaseModel):
    run_id: Optional[UUID] = Field(None, description="ID запуска траектории")
    trajectory_id: Optional[UUID] = Field(None, description="ID траектории RL")
    evaluator_id: str = Field(..., description="ID асессора или пользователя")
    score: float = Field(..., ge=-1.0, le=1.0, description="Скалярная награда в диапазоне [-1.0, 1.0]")
    feedback_type: str = Field("EXPERT", description="Тип оценки: EXPERT, USER, AUTOMATED")
    target_type: str = Field("RUN", description="Объект оценки: RUN, ACTION, EVIDENCE")
    target_id: Optional[UUID] = Field(None, description="ID конкретного таргета (если применимо)")
    comment: Optional[str] = Field(None, description="Комментарий к оценке")


class ActionFeedbackPayload(BaseModel):
    decision_id: UUID = Field(..., description="ID принятого решения/шага политики")
    preferred_action: str = Field(..., min_length=1, description="Предпочтительное действие по мнению эксперта")
    rejected_action: Optional[str] = Field(None, description="Отвергнутое действие")
    comment: Optional[str] = Field(None, description="Комментарий к корректировке")


class EvidenceFeedbackPayload(BaseModel):
    evidence_id: UUID = Field(..., description="ID найденного чанка/фрагмента контекста")
    is_relevant: bool = Field(..., description="Флаг релевантности фрагмента")
    score: float = Field(..., ge=0.0, le=1.0, description="Оценка качества отрывка от 0.0 до 1.0")
    comment: Optional[str] = Field(None, description="Комментарий")


class CorrectionFeedbackPayload(BaseModel):
    corrected_answer: str = Field(..., min_length=1, description="Идеальный исправленный ответ (Golden Answer)")
    comment: Optional[str] = Field(None, description="Замечания к оригинальному ответу")


class FeedbackResponse(BaseModel):
    feedback_id: UUID = Field(..., description="Уникальный ID принятого фидбека")
    run_id: UUID = Field(..., description="ID связанного запуска")
    target_type: str = Field(..., description="Тип цели фидбека (RUN, ACTION, EVIDENCE)")
    target_id: Optional[UUID] = Field(None, description="ID цели фидбека")
    status: str = Field("ACCEPTED", description="Статус обработки отзыва")
    received_at: datetime = Field(..., description="Время фиксации отзыва")


class HumanFeedbackResponse(BaseModel):
    feedback_id: UUID
    status: str
    assigned_reward: float