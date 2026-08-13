import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.persistence.models import OutboxMessageModel

logger = logging.getLogger(__name__)


class MessageProducer(Protocol):
    async def publish(self, topic: str, key: str, payload: dict) -> None:
        ...


class OutboxPublisher:
    """Background worker для чтения необработанных событий из transactional_outbox и их отправки в шину данных."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        producer: MessageProducer,
        batch_size: int = 50,
        poll_interval_seconds: float = 2.0,
    ):
        self._session_factory = session_factory
        self._producer = producer
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запускает фоновый воркер публикаций."""
        if self._is_running:
            logger.warning("OutboxPublisher is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._publishing_loop())
        logger.info("OutboxPublisher background worker started.")

    async def stop(self) -> None:
        """Останавливает фоновый воркер."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("OutboxPublisher background worker stopped.")

    async def _publishing_loop(self) -> None:
        while self._is_running:
            try:
                processed_count = await self.process_outbox_batch()
                if processed_count == 0:
                    await asyncio.sleep(self._poll_interval)
            except Exception as err:
                logger.error(f"Error in OutboxPublisher loop: {err}", exc_info=True)
                await asyncio.sleep(self._poll_interval)

    async def process_outbox_batch(self) -> int:
        """Берет пачку PENDING событий с FOR UPDATE SKIP LOCKED и отправляет в брокер."""
        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    select(OutboxMessageModel)
                    .where(OutboxMessageModel.status == "PENDING")
                    .order_by(OutboxMessageModel.created_at.asc())
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
                result = await session.execute(stmt)
                events = result.scalars().all()

                if not events:
                    return 0

                for event in events:
                    try:
                        # event.event_type имеет тип EventType (StrEnum)
                        topic = f"events.{str(event.event_type).lower()}"
                        await self._producer.publish(
                            topic=topic,
                            key=str(event.aggregate_id),
                            payload=event.payload,
                        )
                        event.status = "PROCESSED"
                        event.processed_at = datetime.now(timezone.utc)
                    except Exception as pub_err:
                        logger.error(f"Failed to publish outbox event {event.id}: {pub_err}")
                        event.retry_count += 1
                        event.error = str(pub_err)  # Исправлено имя атрибута
                        if event.retry_count >= 5:
                            event.status = "FAILED"

                return len(events)