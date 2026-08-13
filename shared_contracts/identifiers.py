from uuid import UUID
from pydantic import BaseModel, Field

class CorrelationIds(BaseModel):
    run_id: UUID
    trajectory_id: UUID
    state_id: UUID | None = None
    action_id: UUID | None = None
    policy_decision_id: UUID | None = None
    reasoning_graph_id: UUID | None = None
    reasoning_node_id: UUID | None = None
    evidence_id: UUID | None = None
    feedback_id: UUID | None = None
    transition_id: UUID | None = None

class VersionVector(BaseModel):
    event_schema_version: int = 1
    observation_schema_version: str
    action_space_version: str
    reasoning_schema_version: str
    reward_model_version: str | None = None