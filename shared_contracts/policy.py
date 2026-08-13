from enum import StrEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class HierarchyLevel(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class RewardStatus(StrEnum):
    PENDING = "PENDING"
    CALCULATED = "CALCULATED"
    FAILED = "FAILED"


class PolicyDecisionTrace(BaseModel):
    """След (Trace) принятого политикой решения."""
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    hierarchy_level: HierarchyLevel
    action_index: int = Field(..., description="Индекс выбранного действия в Action Space")
    action_name: str = Field(..., description="Человекочитаемое название действия/инструмента")
    q_values: Optional[List[float]] = Field(default=None, description="Значения Q-values для всех действий")
    action_mask: List[bool] = Field(..., description="Маска доступности действий на момент выбора")
    observation_schema_version: str = Field(default="v1.0")
    action_space_version: str = Field(default="v1.0")


class RawRLTransition(BaseModel):
    """Сырой переход (State, Action, Next_State) для сохранения в БД и последующего RL-обучения."""
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    trajectory_id: UUID
    decision_id: UUID
    hierarchy_level: HierarchyLevel
    state: Dict[str, Any]
    action_index: int
    action_name: str
    next_state: Dict[str, Any]
    done: bool
    next_action_mask: List[bool]
    reward_status: RewardStatus = Field(default=RewardStatus.PENDING)
    reward_value: Optional[float] = None
    observation_schema_version: str = Field(default="v1.0")
    action_space_version: str = Field(default="v1.0")