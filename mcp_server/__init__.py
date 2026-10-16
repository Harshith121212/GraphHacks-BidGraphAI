"""MCP Server package initialization."""

from mcp_server.server import (
    mcp,
    get_active_tenders_and_sync_status,
    discover_direct_and_lookalike_matches,
    discover_jv_consortium_matches,
    dispatch_tender_alert_with_trace,
    record_bid_outcome_and_learn,
    execute_read_cypher,
    get_alerts_and_agent_memory,
    get_graph_visualization_snapshot,
    enrich_and_ingest_tender,
    reset_and_seed_demo_graph,
)

__all__ = [
    "mcp",
    "get_active_tenders_and_sync_status",
    "discover_direct_and_lookalike_matches",
    "discover_jv_consortium_matches",
    "dispatch_tender_alert_with_trace",
    "record_bid_outcome_and_learn",
    "execute_read_cypher",
    "get_alerts_and_agent_memory",
    "get_graph_visualization_snapshot",
    "enrich_and_ingest_tender",
    "reset_and_seed_demo_graph",
]
