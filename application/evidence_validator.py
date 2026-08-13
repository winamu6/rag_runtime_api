from dataclasses import dataclass
from typing import List, Set
from uuid import UUID


@dataclass(frozen=True)
class RetrievedEntity:
    entity_id: UUID
    source_type: str
    content_hash: str


class InvalidEvidenceError(Exception):
    """Вызывается при попытке сослаться на незагруженный или фиктивный источник."""
    pass


class EvidenceValidator:
    def validate_evidences(
        self,
        claimed_evidence_ids: List[UUID],
        retrieved_entities: List[RetrievedEntity],
    ) -> List[UUID]:
        valid_set: Set[UUID] = {e.entity_id for e in retrieved_entities}
        verified_ids: List[UUID] = []

        for evidence_id in claimed_evidence_ids:
            if evidence_id not in valid_set:
                raise InvalidEvidenceError(
                    f"Evidence {evidence_id} was claimed by agent, but not found in retrieval results!"
                )
            verified_ids.append(evidence_id)

        return verified_ids