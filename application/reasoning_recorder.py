from datetime import datetime, timezone
from typing import Any, Dict, Protocol, List
from uuid import UUID, uuid4

from shared_contracts.reasoning import (
    ReasoningEdge,
    ReasoningNode,
    ReasoningNodeType,
)


class ReasoningRepository(Protocol):
    async def add_node(self, node: ReasoningNode) -> None:
        ...

    async def add_edge(self, edge: ReasoningEdge) -> None:
        ...


class ReasoningGraphRecorder:
    def __init__(self, repository: ReasoningRepository):
        self._repo = repository

    async def record_node(
        self,
        graph_id: UUID,
        run_id: UUID,
        trajectory_id: UUID,
        node_type: ReasoningNodeType,
        structured_payload: Dict[str, Any],
    ) -> ReasoningNode:
        """
        Записывает структурированный узел графа рассуждений.
        ВАЖНО: payload должен содержать только факты, гипотезы и вызовы инструментов.
        Скрытый chain-of-thought сюда НЕ передается (Раздел 4.6).
        """
        node = ReasoningNode(
            id=uuid4(),
            graph_id=graph_id,
            run_id=run_id,
            trajectory_id=trajectory_id,
            node_type=node_type,
            structured_payload=structured_payload,
            created_at=datetime.now(timezone.utc),
        )
        await self._repo.add_node(node)
        return node

    async def record_edge(
        self,
        graph_id: UUID,
        source_node_id: UUID,
        target_node_id: UUID,
        relation: str,
    ) -> ReasoningEdge:
        """Записывает ориентированное ребро между узлами графа."""
        edge = ReasoningEdge(
            id=uuid4(),
            graph_id=graph_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation=relation,
            created_at=datetime.now(timezone.utc),
        )
        await self._repo.add_edge(edge)
        return edge