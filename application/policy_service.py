import logging
from typing import Any, Dict, List, Protocol, Optional
from uuid import uuid4

from shared_contracts.policy import HierarchyLevel, PolicyDecisionTrace

logger = logging.getLogger(__name__)

class ActionSpaceRegistry(Protocol):
    """Реестр доступных действий для каждого уровня иерархии."""

    def get_action_names(self, hierarchy_level: HierarchyLevel) -> List[str]:
        ...

    def get_action_mask(
        self, hierarchy_level: HierarchyLevel, state: Any
    ) -> List[bool]:
        ...


class ObservationEncoder(Protocol):
    """Кодировщик состояния в формат наблюдения для модели."""

    @property
    def schema_version(self) -> str:
        ...

    def encode(self, state: Any) -> Dict[str, Any]:
        ...


class PolicyModelEvaluator(Protocol):
    """Нейросетевая модель / Инференс-движок политики (Q-Network / Actor)."""

    @property
    def action_space_version(self) -> str:
        ...

    async def predict_action(
        self,
        hierarchy_level: HierarchyLevel,
        observation: Dict[str, Any],
        action_mask: List[bool],
    ) -> tuple[int, Optional[List[float]]]:
        """
        Возвращает:
          - action_index: выбранный индекс действия
          - q_values: опциональный список Q-значений для всех действий
        """
        ...


class RuntimePolicyService:
    def __init__(
        self,
        action_registry: ActionSpaceRegistry,
        observation_encoder: ObservationEncoder,
        model_evaluator: PolicyModelEvaluator,
    ):
        self._action_registry = action_registry
        self._encoder = observation_encoder
        self._evaluator = model_evaluator

    async def select_action(
        self, state: Any, hierarchy_level: HierarchyLevel
    ) -> PolicyDecisionTrace:
        """
        Формирует срез наблюдения, рассчитывает маску допустимых действий
        и выбирает оптимальное действие с помощью инференс-модели политики.
        """
        action_names = self._action_registry.get_action_names(hierarchy_level)
        if not action_names:
            raise ValueError(
                f"No actions registered for hierarchy level: {hierarchy_level}"
            )

        action_mask = self._action_registry.get_action_mask(hierarchy_level, state)
        if not any(action_mask):
            logger.error(
                f"All actions are masked out for hierarchy level {hierarchy_level}. State: {state}"
            )
            raise RuntimeError(
                f"Invalid state: No valid actions available for level {hierarchy_level}"
            )

        encoded_observation = self._encoder.encode(state)

        action_index, q_values = await self._evaluator.predict_action(
            hierarchy_level=hierarchy_level,
            observation=encoded_observation,
            action_mask=action_mask,
        )

        if action_index < 0 or action_index >= len(action_names):
            raise IndexError(
                f"Predicted action_index {action_index} out of bounds for action space of size {len(action_names)}"
            )

        if not action_mask[action_index]:
            logger.warning(
                f"Model predicted masked action at index {action_index} ('{action_names[action_index]}'). Fallback to first valid action."
            )
            action_index = action_mask.index(True)

        selected_action_name = action_names[action_index]

        decision_trace = PolicyDecisionTrace(
            id=uuid4(),
            hierarchy_level=hierarchy_level,
            action_index=action_index,
            action_name=selected_action_name,
            q_values=q_values,
            action_mask=action_mask,
            observation_schema_version=self._encoder.schema_version,
            action_space_version=self._evaluator.action_space_version,
        )

        logger.info(
            f"[PolicyService] Selected action '{selected_action_name}' (Index {action_index}) for level {hierarchy_level}"
        )

        return decision_trace