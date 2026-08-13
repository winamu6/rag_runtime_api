from uuid import uuid4
import pytest
from sqlalchemy import select

from infrastructure.messaging.outbox_publisher import OutboxPublisher
from infrastructure.persistence.models import OutboxMessageModel

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("setup_database")]


async def test_outbox_publisher_processes_pending_events(
    session_factory, mock_producer
):
    aggregate_id = uuid4()

    async with session_factory() as session:
        event = OutboxMessageModel(
            id=uuid4(),
            aggregate_id=aggregate_id,
            event_type="ExecutionCompletedEvent",
            payload={"run_id": "run_100", "status": "COMPLETED"},
            status="PENDING",
            retry_count=0,
        )
        session.add(event)
        await session.commit()

    publisher = OutboxPublisher(
        session_factory=session_factory,
        producer=mock_producer,
        poll_interval_seconds=0.1,
    )
    processed_count = await publisher.process_outbox_batch()

    assert processed_count == 1
    mock_producer.publish.assert_called_once()

    async with session_factory() as session:
        stmt = select(OutboxMessageModel).where(
            OutboxMessageModel.aggregate_id == aggregate_id
        )
        result = await session.execute(stmt)
        updated_event = result.scalar_one()

        assert updated_event.status == "PROCESSED"
        assert updated_event.processed_at is not None