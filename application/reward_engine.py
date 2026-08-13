import logging
from typing import List, Protocol, Optional, Dict, Any
from uuid import UUID

from shared_contracts.policy import RawRLTransition, RewardStatus

logger = logging.getLogger(__name__)

class RewardCalculator(Protocol):
    """Стратегия расчета вознаграждений для прогона/траектории."""

    async def calculate_trajectory_rewards(
        self, transitions: List[RawRLTransition], final_answer: str, user_feedback: Optional[float] = None
    ) -> List[float]:
        """Возвращает список рассчитанных наград R_t для каждого шага траектории."""
        ...


class RewardRepository(Protocol):
    """Репозиторий для массового обновления наград в базе данных."""

    async def fetch_pending_transitions(self, run_id: UUID) -> List[RawRLTransition]:
        ...

    async def update_transition_rewards(
        self, transition_rewards: Dict[UUID, float]
    ) -> None:
        ...


class RewardUnitOfWork(Protocol):
    rewards: RewardRepository

    def transaction(self):
        ...

class DefaultRewardCalculator:
    """
    Базовая стратегия расчета вознаграждения:
    - Штраф за каждый шаг (Step penalty), стимулирующий минимальную длину решения.
    - Итоговый бонус/штраф за корректность ответа (Sparse final reward).
    - Дисконтирование наград назад по траектории (Discounted Reward Backpropagation).
    """

    def __init__(
        self,
        step_penalty: float = -0.05,
        base_success_reward: float = 1.0,
        gamma: float = 0.99,
    ):
        self._step_penalty = step_penalty
        self._base_success_reward = base_success_reward
        self._gamma = gamma

    async def calculate_trajectory_rewards(
        self,
        transitions: List[RawRLTransition],
        final_answer: str,
        user_feedback: Optional[float] = None,
    ) -> List[float]:
        if not transitions:
            return []

        num_steps = len(transitions)
        raw_rewards = [self._step_penalty] * num_steps

        final_reward = self._base_success_reward
        if user_feedback is not None:
            final_reward = user_feedback
        elif not final_answer or "error" in final_answer.lower():
            final_reward = -1.0

        raw_rewards[-1] += final_reward

        discounted_rewards = [0.0] * num_steps
        running_add = 0.0
        for t in reversed(range(num_steps)):
            running_add = raw_rewards[t] + self._gamma * running_add
            discounted_rewards[t] = round(running_add, 4)

        return discounted_rewards

class RewardEngine:
    def __init__(
        self,
        uow_factory: Any,
        calculator: Optional[RewardCalculator] = None,
    ):
        self._uow_factory = uow_factory
        self._calculator = calculator or DefaultRewardCalculator()

    async def process_run_rewards(
        self,
        run_id: UUID,
        final_answer: str,
        user_feedback: Optional[float] = None,
    ) -> int:
        """
        Извлекает необработанные переходы прогона, рассчитывает для них
        значения вознаграждений R_t и атомарно сохраняет их в БД.
        """
        async with self._uow_factory.transaction() as uow:
            transitions = await uow.rewards.fetch_pending_transitions(run_id)

            if not transitions:
                logger.info(f"[RewardEngine] No pending transitions found for Run {run_id}.")
                return 0

            # Расчет наград
            rewards = await self._calculator.calculate_trajectory_rewards(
                transitions=transitions,
                final_answer=final_answer,
                user_feedback=user_feedback,
            )

            updates: Dict[UUID, float] = {
                t.id: r for t, r in zip(transitions, rewards)
            }

            await uow.rewards.update_transition_rewards(updates)
            logger.info(
                f"[RewardEngine] Successfully updated rewards for {len(updates)} transitions in Run {run_id}."
            )

            return len(updates)