import hashlib
import pytest
from infrastructure.model_provider.artifacts import (
    LoadedModel,
    ModelChecksumMismatchError,
)


def test_artifact_loader_sha256_mismatch():
    fake_bytes = b"model_weights_data"
    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(ModelChecksumMismatchError):
        LoadedModel.verify_sha256(fake_bytes, wrong_hash)


def test_artifact_loader_sha256_success():
    fake_bytes = b"model_weights_data"
    correct_hash = hashlib.sha256(fake_bytes).hexdigest()

    LoadedModel.verify_sha256(fake_bytes, correct_hash)