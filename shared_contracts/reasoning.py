from enum import StrEnum
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class ReasoningNodeType(StrEnum):
    OBSERVATION = "observation"
    POLICY_DECISION = "policy_decision"
    ACTION = "action"
    TOOL_CALL = "tool_call"
    EVIDENCE = "evidence"
    REFLECTION = "reflection"
    HYPOTHESIS = "hypothesis"
    GAP = "gap"
    AGENT_RESULT = "agent_result"
    COMPLETION = "completion"

class ReasoningNode(BaseModel):
    id: UUID
    graph_id: UUID
    run_id: UUID
    trajectory_id: UUID
    node_type: ReasoningNodeType
    structured_payload: dict
    created_at: datetime

class ReasoningEdge(BaseModel):
    id: UUID
    graph_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relation: str
    created_at: datetime