"""Database schema initialization: Cypher indexes and constraints for FalkorDB."""

import logging
from typing import List, Tuple, Dict, Any
from falkordb import Graph

logger = logging.getLogger(__name__)

INDEX_SPECIFICATIONS: List[Tuple[str, str]] = [
    ("Ministry", "id"),
    ("Department", "id"),
    ("Tender", "id"),
    ("Tender", "status"),
    ("Client", "id"),
    ("Client", "is_blacklisted"),
    ("WorkCategory", "name"),
    ("Specialization", "name"),
    ("Certification", "name"),
    ("Brand", "name"),
    ("Product", "name"),
    ("EnlistmentClass", "code"),
    ("Region", "name"),
    ("AgentDecision", "id"),
    ("SystemMeta", "key"),
]


def initialize_schema(graph: Graph) -> Dict[str, Any]:
    """
    Idempotently creates indexes on FalkorDB node labels and key properties.
    Ensures O(1) / O(log N) lookups for multi-hop traversals and filters.
    """
    created_indexes = []
    existing_indexes = []
    errors = []

    for label, prop in INDEX_SPECIFICATIONS:
        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            graph.query(query)
            created_indexes.append(f"{label}.{prop}")
            logger.info("Created index for %s.%s", label, prop)
        except Exception as exc:
            err_msg = str(exc)
            if "already indexed" in err_msg.lower() or "index already exists" in err_msg.lower():
                existing_indexes.append(f"{label}.{prop}")
            else:
                logger.warning("Failed to create index for %s.%s: %s", label, prop, err_msg)
                errors.append({"index": f"{label}.{prop}", "error": err_msg})

    return {
        "status": "success" if not errors else "partial",
        "created": created_indexes,
        "existing": existing_indexes,
        "errors": errors,
    }
