import asyncio
import io
import logging
from typing import Dict, Optional
from uuid import UUID

import torch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from shared_contracts.policy import HierarchyLevel
from shared_contracts.model_registry import CheckpointStatus
from infrastructure.model_provider.artifacts import (
    LoadedModel,
    ModelChecksumMismatchError,
)

logger = logging.getLogger(__name__)


class ActiveModelProvider:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        poll_interval_seconds: int = 10,
        fallback_policy: Optional["ActiveModelProvider"] = None,
    ):
        self._session_factory = session_factory
        self._poll_interval = poll_interval_seconds
        self._fallback_policy = fallback_policy
        self._active_models: Dict[HierarchyLevel, LoadedModel] = {}
        self._poll_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        await self.reload_active_models()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def get_active_model(self, hierarchy_level: HierarchyLevel) -> LoadedModel:
        loaded = self._active_models.get(hierarchy_level)
        if not loaded:
            if self._fallback_policy:
                logger.warning(
                    f"No active model found for {hierarchy_level}. Falling back to configured fallback policy."
                )
                return await self._fallback_policy.get_active_model(hierarchy_level)
            raise RuntimeError(f"No active model or fallback available for hierarchy level '{hierarchy_level}'.")
        return loaded

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            try:
                await self.reload_active_models()
            except Exception as e:
                logger.error(f"Error during Model Registry polling: {e}", exc_info=True)

    async def reload_active_models(self) -> None:
        async with self._session_factory() as session:
            for level in HierarchyLevel:
                checkpoint_data = await self._fetch_active_checkpoint_metadata(session, level)
                if not checkpoint_data:
                    continue

                current_loaded = self._active_models.get(level)
                if current_loaded and current_loaded.checkpoint_id == checkpoint_data["checkpoint_id"]:
                    continue

                try:
                    new_loaded_model = await self._load_and_verify_checkpoint(checkpoint_data, level)
                    self._active_models[level] = new_loaded_model
                    logger.info(
                        f"Successfully promoted and loaded ACTIVE model checkpoint {new_loaded_model.checkpoint_id} for level {level}."
                    )
                except Exception as err:
                    logger.error(
                        f"Failed to reload checkpoint {checkpoint_data.get('checkpoint_id')} for {level}. "
                        f"Retaining previously loaded model. Error: {err}"
                    )

    async def _load_and_verify_checkpoint(self, metadata: dict, level: HierarchyLevel) -> LoadedModel:
        """Скачивает артефакт, проверяет SHA256 и десериализует строго без optimizer/replay."""
        artifact_bytes = await self._download_artifact_bytes(metadata["artifact_uri"])

        LoadedModel.verify_sha256(artifact_bytes, metadata["artifact_sha256"])

        buffer = io.BytesIO(artifact_bytes)

        raw_model = torch.load(buffer, map_location="cpu", weights_only=True)
        raw_model.eval()

        return LoadedModel(
            checkpoint_id=metadata["checkpoint_id"],
            hierarchy_level=level,
            model=raw_model,
            observation_schema_version=metadata["observation_schema_version"],
            action_space_version=metadata["action_space_version"],
            artifact_sha256=metadata["artifact_sha256"],
        )

    async def _fetch_active_checkpoint_metadata(self, session, level: HierarchyLevel) -> Optional[dict]:
        return None

    async def _download_artifact_bytes(self, uri: str) -> bytes:
        return b""