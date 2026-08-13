import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.config import settings
from infrastructure.messaging.outbox_publisher import MessageProducer, OutboxPublisher
from infrastructure.model_provider.active_model_provider import ActiveModelProvider
from infrastructure.persistence.unit_of_work import SQLAlchemyAsyncUnitOfWork

from presentation.api.runs_router import router as runs_router
from presentation.api.feedback_router import router as feedback_router
from presentation.api.feedback_router import get_uow

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("rag_runtime_api")


class StubKafkaProducer(MessageProducer):
    async def publish(self, topic: str, key: str, payload: dict) -> None:
        logger.info(f"[Outbox Event Sent] Topic: {topic} | Key: {key} | Payload: {payload}")


async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

model_provider = ActiveModelProvider(
    session_factory=async_session_factory,
    poll_interval_seconds=settings.MODEL_REGISTRY_POLL_SECONDS,
)
outbox_publisher = OutboxPublisher(
    session_factory=async_session_factory,
    producer=StubKafkaProducer(),
    poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up RAG Runtime API background workers...")
    await model_provider.start()
    await outbox_publisher.start()
    yield
    logger.info("Shutting down RAG Runtime API background workers...")
    await outbox_publisher.stop()
    await model_provider.stop()
    await async_engine.dispose()


app = FastAPI(
    title="RAG Runtime API",
    version="1.0.0",
    lifespan=lifespan,
)


async def override_get_uow() -> SQLAlchemyAsyncUnitOfWork:
    return SQLAlchemyAsyncUnitOfWork(session_factory=async_session_factory)


app.dependency_overrides[get_uow] = override_get_uow
app.include_router(feedback_router)
app.include_router(runs_router)

@app.get("/health", tags=["Health Check"])
async def health_check() -> dict:
    return {"status": "ok", "service": "rag_runtime_api"}