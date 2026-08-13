import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.persistence.repositories import (
    OutboxRepository,
    RunRepository,
    TransitionRepository,
)
from shared_contracts.events import ExecutionCompletedEvent
from shared_contracts.policy import RawRLTransition

logger = logging.getLogger(__name__)


class SQLAlchemyAsyncUnitOfWork:
    """
    Реализация Unit of Work поверх SQLAlchemy AsyncSession.
    Удовлетворяет протоколу UnitOfWork, затребованному в RuntimeChain (Вариант 1).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._session: Optional[AsyncSession] = None

        self.runs: Optional[RunRepository] = None
        self.transitions: Optional[TransitionRepository] = None
        self.outbox: Optional[OutboxRepository] = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator["SQLAlchemyAsyncUnitOfWork", None]:
        """
        Асинхронный контекстный менеджер управления транзакцией.
        Обеспечивает rollback при исключениях и автокомит при успешном завершении блока.
        """
        self._session = self._session_factory()
        self.runs = RunRepository(self._session)
        self.transitions = TransitionRepository(self._session)
        self.outbox = OutboxRepository(self._session)

        try:
            yield self
            await self._session.commit()
            logger.debug("UnitOfWork transaction committed successfully.")
        except Exception as exc:
            await self._session.rollback()
            logger.error(f"UnitOfWork transaction rolled back due to error: {exc}")
            raise
        finally:
            await self._session.close()
            self._session = None
            self.runs = None
            self.transitions = None
            self.outbox = None

    async def mark_run_completed(self, run_id: UUID, final_answer: str) -> None:
        if not self.runs:
            raise RuntimeError("UnitOfWork is not active. Use 'async with uow.transaction():'")
        await self.runs.mark_completed(
            run_id=run_id,
            final_answer=final_answer,
            completed_at=datetime.now(timezone.utc),
        )

    async def add_transitions(self, transitions: List[RawRLTransition]) -> None:
        if not self.transitions:
            raise RuntimeError("UnitOfWork is not active. Use 'async with uow.transaction():'")
        if transitions:
            await self.transitions.add_transitions(transitions)

    async def add_outbox_event(self, event: ExecutionCompletedEvent) -> None:
        if not self.outbox:
            raise RuntimeError("UnitOfWork is not active. Use 'async with uow.transaction():'")
        await self.outbox.add_event(event=event, aggregate_id=event.run_id)