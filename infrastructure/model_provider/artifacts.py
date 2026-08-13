import hashlib
from dataclasses import dataclass
from uuid import UUID
import torch

from shared_contracts.policy import HierarchyLevel


class ModelIncompatibilityError(Exception):
    """Вызывается при несоответствии версий схем наблюдений или пространства действий."""
    pass


class ModelChecksumMismatchError(Exception):
    """Вызывается при несовпадении SHA256 артефакта с записью в Model Registry."""
    pass


@dataclass(frozen=True)
class LoadedModel:
    checkpoint_id: UUID
    hierarchy_level: HierarchyLevel
    model: torch.nn.Module
    observation_schema_version: str
    action_space_version: str
    artifact_sha256: str

    def assert_compatible(
        self, observation_schema_version: str, action_space_version: str
    ) -> None:
        """Проверяет совместимость схемы текущего состояния и пространства действий с моделью."""
        if self.observation_schema_version != observation_schema_version:
            raise ModelIncompatibilityError(
                f"Observation schema mismatch! Model requires '{self.observation_schema_version}', "
                f"got '{observation_schema_version}'."
            )
        if self.action_space_version != action_space_version:
            raise ModelIncompatibilityError(
                f"Action space mismatch! Model requires '{self.action_space_version}', "
                f"got '{action_space_version}'."
            )

    @staticmethod
    def verify_sha256(file_bytes: bytes, expected_sha256: str) -> None:
        """Валидирует целостность бинарника артефакта по SHA256."""
        computed_sha = hashlib.sha256(file_bytes).hexdigest()
        if computed_sha.lower() != expected_sha256.lower():
            raise ModelChecksumMismatchError(
                f"Corrupted artifact! Expected SHA256 '{expected_sha256}', calculated '{computed_sha}'."
            )