from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, Field

class FeedbackTargetType(StrEnum):
    RUN = "run"
    TRAJECTORY = "trajectory"
    ANSWER = "answer"
    AGENT_RESULT = "agent_result"
    POLICY_DECISION = "policy_decision"
    ACTION = "action"
    REFLECTION = "reflection"
    HYPOTHESIS = "hypothesis"
    EVIDENCE = "evidence"
    REASONING_NODE = "reasoning_node"

class HumanFeedbackRequest(BaseModel):
    run_id: UUID
    target_type: FeedbackTargetType
    target_id: UUID | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    comment: str | None = None
    corrected_answer: str | None = None
    preferred_action: str | None = None
    rejected_action: str | None = None
    confirmed_resolution: bool | None = None
    successful_remediation: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)