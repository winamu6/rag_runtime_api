import logging
from datetime import datetime, timezone
from typing import Any, List, Protocol, Optional
from uuid import UUID, uuid4

from shared_contracts.events import ExecutionCompletedEvent
from shared_contracts.policy import (
    HierarchyLevel,
    PolicyDecisionTrace,
    RawRLTransition,
    RewardStatus,
)

logger = logging.getLogger(__name__)


class PolicyService(Protocol):
    async def select_action(
        self, state: Any, hierarchy_level: HierarchyLevel
    ) -> PolicyDecisionTrace:
        ...


class ActionExecutor(Protocol):
    async def execute_action(
        self, action_name: str, state: Any, metadata: dict
    ) -> Any:
        ...


class CancellationToken(Protocol):
    def is_cancelled(self, run_id: UUID) -> bool:
        ...


class UnitOfWork(Protocol):
    async def mark_run_completed(self, run_id: UUID, final_answer: str) -> None:
        ...

    async def add_transitions(self, transitions: List[RawRLTransition]) -> None:
        ...

    async def add_outbox_event(self, event: ExecutionCompletedEvent) -> None:
        ...

    def transaction(self):
        ...


class RuntimeChain:
    def __init__(
        self,
        policy_service: PolicyService,
        action_executor: ActionExecutor,
        unit_of_work: UnitOfWork,
        cancellation_token: Optional[CancellationToken] = None,
        max_steps: int = 15,
    ):
        self._policy_service = policy_service
        self._action_executor = action_executor
        self._uow = unit_of_work
        self._cancellation_token = cancellation_token
        self._max_steps = max_steps

    async def execute_run(self, run_id: UUID, initial_state: Any) -> str:
        """
        Основной цикл выполнения траектории агента.
        Проходит по двухуровневому циклу принятия решений (High/Low level)
        и аккумулирует переходы RawRLTransition для офлайн-обучения.
        """
        trajectory_id = uuid4()
        current_state = initial_state
        raw_transitions: List[RawRLTransition] = []
        final_answer = ""
        step_count = 0

        logger.info(
            f"Starting RuntimeChain execution. RunID: {run_id}, TrajectoryID: {trajectory_id}"
        )

        try:
            while step_count < self._max_steps:
                step_count += 1
                self._check_cancellation(run_id)

                high_trace = await self._policy_service.select_action(
                    state=current_state,
                    hierarchy_level=HierarchyLevel.HIGH,
                )

                logger.debug(
                    f"[Run {run_id}] Step {step_count}: Selected High Action '{high_trace.action_name}'"
                )

                # Если High-level выбрал завершение (FINAL_ANSWER)
                if high_trace.action_name == "FINAL_ANSWER":
                    final_answer = getattr(
                        current_state, "current_answer", "Task execution finished."
                    )
                    break

                self._check_cancellation(run_id)

                low_trace = await self._policy_service.select_action(
                    state=current_state,
                    hierarchy_level=HierarchyLevel.LOW,
                )

                logger.debug(
                    f"[Run {run_id}] Step {step_count}: Selected Low Action '{low_trace.action_name}'"
                )

                next_state = await self._action_executor.execute_action(
                    action_name=low_trace.action_name,
                    state=current_state,
                    metadata={"run_id": run_id, "trace_id": low_trace.id},
                )

                is_done = (step_count >= self._max_steps) or (
                    getattr(next_state, "is_terminal", False)
                )

                transition = RawRLTransition(
                    id=uuid4(),
                    run_id=run_id,
                    trajectory_id=trajectory_id,
                    decision_id=low_trace.id,
                    hierarchy_level=HierarchyLevel.LOW,
                    state=current_state.policy_observation,
                    action_index=low_trace.action_index,
                    action_name=low_trace.action_name,
                    next_state=next_state.policy_observation,
                    done=is_done,
                    next_action_mask=getattr(
                        next_state, "next_action_mask", [True] * len(low_trace.action_mask)
                    ),
                    reward_status=RewardStatus.PENDING,
                    observation_schema_version=low_trace.observation_schema_version,
                    action_space_version=low_trace.action_space_version,
                )
                raw_transitions.append(transition)

                current_state = next_state

                if is_done:
                    final_answer = getattr(
                        current_state, "current_answer", "Execution reached terminal state."
                    )
                    break

            completed_event = ExecutionCompletedEvent(
                event_id=uuid4(),
                run_id=run_id,
                trajectory_id=trajectory_id,
                total_steps=step_count,
                final_answer=final_answer,
                completed_at=datetime.now(timezone.utc),
            )

            async with self._uow.transaction():
                await self._uow.mark_run_completed(run_id, final_answer)
                await self._uow.add_transitions(raw_transitions)
                await self._uow.add_outbox_event(completed_event)

            logger.info(f"Run {run_id} successfully executed in {step_count} steps.")
            return final_answer

        except Exception as exc:
            logger.error(f"Run {run_id} failed with error: {exc}", exc_info=True)
            raise

    def _check_cancellation(self, run_id: UUID) -> None:
        """Проверяет, не поступала ли команда отмены выполнения."""
        if self._cancellation_token and self._cancellation_token.is_cancelled(run_id):
            logger.warning(f"Execution of Run {run_id} was cancelled.")
            raise RuntimeError(f"Run {run_id} was cancelled by user request.")