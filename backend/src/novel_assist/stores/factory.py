from __future__ import annotations

import os

from novel_assist.stores.graph_store import GraphStore
from novel_assist.stores.jsonl_graph_store import JsonlGraphStore
from novel_assist.stores.neo4j_graph_store import Neo4jGraphStore


def get_graph_store() -> GraphStore:
    backend = os.getenv("GRAPH_STORE_BACKEND", "jsonl").strip().lower()
    if backend == "neo4j":
        return Neo4jGraphStore()
    return JsonlGraphStore()


def reset_graph_store() -> None:
    return None
