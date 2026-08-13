import asyncio
import logging
from typing import List, Optional, Protocol
from uuid import UUID

from shared_contracts.events import OutboxMessage

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Абстракции внешних сервисов (DIP)
# ----------------------------------------------------------------------
class EventPublisher(Protocol):
    """Интерфейс публикации сообщений в шину (RabbitMQ / Kafka / NATS)."""

    async def publish(self, event_type: str, payload: dict, message_id: UUID) -> None:
        ...


class OutboxRepositoryProtocol(Protocol):
    """Интерфейс репозитория для работы с Outbox таблицей."""

    async def fetch_pending_messages(self, batch_size: int) -> List[OutboxMessage]:
        ...

    async def mark_as_processed(self, message_ids: List[UUID]) -> None:
        ...

    async def mark_as_failed(
        self, message_id: UUID, error_reason: str, retry_count: int
    ) -> None:
        ...


class OutboxUnitOfWorkProtocol(Protocol):
    """Unit of Work для фоновой задачи Outbox."""

    outbox: OutboxRepositoryProtocol

    def transaction(self):
        ...


# ----------------------------------------------------------------------
# Реализация Outbox Processor (Background Worker)
# ----------------------------------------------------------------------
class OutboxProcessor:
    def __init__(
        self,
        uow_factory: any,
        publisher: EventPublisher,
        batch_size: int = 50,
        poll_interval_seconds: float = 2.0,
        max_retries: int = 5,
    ):
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._max_retries = max_retries
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запуск фонового воркера (синтаксис исправлен)."""
        if self._is_running:
            logger.warning("OutboxProcessor is already running.")
            return

        self._is_running = True
        self._worker_task = asyncio.create_task(self._run_loop())
        logger.info("OutboxProcessor started.")

    async def stop(self) -> None:
        """Мягкая остановка фонового воркера."""
        if not self._is_running:
            return

        logger.info("Stopping OutboxProcessor...")
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("OutboxProcessor stopped.")

    async def process_batch(self) -> int:
        """
        Обработка одного пакета сообщений (Batch Execution).
        Возвращает количество успешно обработанных событий.
        """
        async with self._uow_factory.transaction() as uow:
            pending_messages: List[OutboxMessage] = (
                await uow.outbox.fetch_pending_messages(
                    batch_size=self._batch_size
                )
            )

            if not pending_messages:
                return 0

            logger.debug(
                f"[Outbox] Fetched {len(pending_messages)} pending events."
            )
            processed_ids: List[UUID] = []

            for msg in pending_messages:
                try:
                    await self._publisher.publish(
                        event_type=msg.event_type,
                        payload=msg.payload,
                        message_id=msg.id,
                    )
                    processed_ids.append(msg.id)

                except Exception as exc:
                    logger.error(
                        f"[Outbox] Failed to publish message {msg.id} (Type: {msg.event_type}). Error: {exc}",
                        exc_info=True,
                    )
                    await uow.outbox.mark_as_failed(
                        message_id=msg.id,
                        error_reason=str(exc),
                        retry_count=msg.retry_count + 1,
                    )

            if processed_ids:
                await uow.outbox.mark_as_processed(processed_ids)
                logger.info(
                    f"[Outbox] Successfully processed {len(processed_ids)} events."
                )

            return len(processed_ids)

    async def _run_loop(self) -> None:
        """Главный асинхронный цикл опроса таблицы Outbox."""
        while self._is_running:
            try:
                processed_count = await self.process_batch()
                if processed_count < self._batch_size:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    f"[Outbox] Unexpected error in processing loop: {exc}",
                    exc_info=True,
                )
                await asyncio.sleep(self._poll_interval)