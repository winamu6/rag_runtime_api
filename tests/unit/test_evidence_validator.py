from uuid import uuid4
import pytest

from application.evidence_validator import (
    EvidenceValidator,
    InvalidEvidenceError,
    RetrievedEntity,
)


def test_evidence_validation_success():
    validator = EvidenceValidator()
    doc_id = uuid4()
    extracted_entities = [
        RetrievedEntity(
            entity_id=doc_id, source_type="confluence", content_hash="hash123"
        )
    ]
    claimed_ids = [doc_id]

    verified = validator.validate_evidences(
        claimed_evidence_ids=claimed_ids, retrieved_entities=extracted_entities
    )
    assert verified == claimed_ids


def test_evidence_validation_hallucination_raises_exception():
    validator = EvidenceValidator()
    doc_id = uuid4()
    fake_id = uuid4()
    extracted_entities = [
        RetrievedEntity(
            entity_id=doc_id, source_type="confluence", content_hash="hash123"
        )
    ]
    claimed_ids = [doc_id, fake_id]

    with pytest.raises(InvalidEvidenceError) as exc_info:
        validator.validate_evidences(
            claimed_evidence_ids=claimed_ids, retrieved_entities=extracted_entities
        )

    assert str(fake_id) in str(exc_info.value)