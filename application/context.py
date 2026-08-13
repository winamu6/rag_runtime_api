from dataclasses import dataclass
from uuid import UUID

from infrastructure.model_provider.active_model_provider import ActiveModelProvider


@dataclass(frozen=True)
class ResearchRuntimeContext:

    run_id: UUID
    trajectory_id: UUID
    reasoning_graph_id: UUID
    model_provider: ActiveModelProvider