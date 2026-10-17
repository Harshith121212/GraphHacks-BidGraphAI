
import os
import sys
import time
import json
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from falkordb import FalkorDB, Graph
from config import get_settings
from db.schema import initialize_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("falkordb_migration")

KEY_PROPERTIES = {
    "Ministry": "id",
    "Department": "id",
    "Tender": "id",
    "Client": "id",
    "WorkCategory": "name",
    "Specialization": "name",
    "Certification": "name",
    "Brand": "name",
    "Product": "name",
    "EnlistmentClass": "code",
    "Region": "name",
    "AgentDecision": "id",
    "JVConsortium": "id",
    "SystemMeta": "key",
}


def cypher_value(val: Any) -> str:
    """Format a Python value as a valid Cypher literal."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return f'"{escaped}"'
    if isinstance(val, list):
        return "[" + ", ".join(cypher_value(x) for x in val) + "]"
    escaped = json.dumps(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def connect_client(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    ssl: bool = False,
    url: Optional[str] = None,
) -> FalkorDB:
    """Connect to a FalkorDB instance with timeout and auto-fallback."""
    if url:
        return FalkorDB.from_url(url)
    kwargs: Dict[str, Any] = {
        "host": host,
        "port": port,
        "socket_timeout": 15,
        "socket_connect_timeout": 8,
    }
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password

    masked_host = host[:6] + "***" + host[-8:] if len(host) > 20 else host
    if ssl:
        try:
            logger.info("Attempting connection to %s:%d with SSL/TLS...", masked_host, port)
            ssl_kwargs = dict(kwargs)
            ssl_kwargs["ssl"] = True
            ssl_kwargs["ssl_cert_reqs"] = None
            ssl_kwargs["ssl_check_hostname"] = False
            client = FalkorDB(**ssl_kwargs)
            client.list_graphs()
            return client
        except Exception as exc:
            logger.warning("SSL connection to %s:%d failed (%s). Falling back to non-SSL...", masked_host, port, exc)

    logger.info("Connecting to %s:%d (plain TCP)...", masked_host, port)
    client = FalkorDB(**kwargs)
    client.list_graphs()
    return client


def migrate_graph(
    source_client: FalkorDB,
    target_client: FalkorDB,
    source_graph_name: str,
    target_graph_name: str,
    clear_target: bool = False,
) -> Dict[str, Any]:
    """Execute complete graph migration from source to target."""
    t_start = time.time()
    source_graph = source_client.select_graph(source_graph_name)
    target_graph = target_client.select_graph(target_graph_name)

    # 1. Clear target if requested
    if clear_target:
        try:
            target_graph.delete()
            logger.info("Cleared existing target graph '%s'", target_graph_name)
            target_graph = target_client.select_graph(target_graph_name)
        except Exception as exc:
            logger.warning("Target graph delete skipped (may be empty): %s", exc)

    # 2. Schema initialization on target
    logger.info("Step 1/4: Initializing indexes and constraints on target...")
    schema_res = initialize_schema(target_graph)
    logger.info("Target schema initialized: %d created, %d existing", len(schema_res.get("created", [])), len(schema_res.get("existing", [])))

    # 3. Extract and Transfer Nodes
    logger.info("Step 2/4: Extracting nodes from '%s'...", source_graph_name)
    nodes_raw = source_graph.query("MATCH (n) RETURN labels(n)[0], properties(n)").result_set
    total_nodes = len(nodes_raw)
    logger.info("Found %d nodes to transfer. Transferring...", total_nodes)

    t_nodes = time.time()
    node_counts_by_label: Dict[str, int] = {}
    for label, props in nodes_raw:
        p_dict = dict(props)
        node_counts_by_label[label] = node_counts_by_label.get(label, 0) + 1
        k_name = KEY_PROPERTIES.get(label, "id")
        k_val = p_dict.get(k_name)
        set_clause = ", ".join(f"n.{k} = {cypher_value(v)}" for k, v in p_dict.items())

        if k_val is not None:
            q = f"MERGE (n:{label} {{{k_name}: {cypher_value(k_val)}}}) SET {set_clause}"
        else:
            q = f"CREATE (n:{label}) SET {set_clause}"
        target_graph.query(q)

    logger.info("Transferred %d nodes in %.2fs", total_nodes, time.time() - t_nodes)

    # 4. Extract and Transfer Relationships
    logger.info("Step 3/4: Extracting relationships from '%s'...", source_graph_name)
    q_edges = """
    MATCH (a)-[r]->(b)
    RETURN 
        labels(a)[0] as src_label,
        coalesce(a.id, a.name, a.code, a.key) as src_key_val,
        labels(b)[0] as tgt_label,
        coalesce(b.id, b.name, b.code, b.key) as tgt_key_val,
        type(r) as rel_type,
        properties(r) as rel_props
    """
    edges_raw = source_graph.query(q_edges).result_set
    total_edges = len(edges_raw)
    logger.info("Found %d edges to transfer. Transferring...", total_edges)

    t_edges = time.time()
    edge_counts_by_type: Dict[str, int] = {}
    for src_label, src_val, tgt_label, tgt_val, rel_type, rel_props in edges_raw:
        edge_counts_by_type[rel_type] = edge_counts_by_type.get(rel_type, 0) + 1
        src_k = KEY_PROPERTIES.get(src_label, "id")
        tgt_k = KEY_PROPERTIES.get(tgt_label, "id")
        p_dict = dict(rel_props)

        if p_dict:
            set_clause = "SET " + ", ".join(f"r.{k} = {cypher_value(v)}" for k, v in p_dict.items())
        else:
            set_clause = ""

        edge_q = f"""
        MATCH (a:{src_label} {{{src_k}: {cypher_value(src_val)}}})
        MATCH (b:{tgt_label} {{{tgt_k}: {cypher_value(tgt_val)}}})
        MERGE (a)-[r:{rel_type}]->(b)
        {set_clause}
        """
        target_graph.query(edge_q)

    logger.info("Transferred %d edges in %.2fs", total_edges, time.time() - t_edges)

    # 5. Verification
    logger.info("Step 4/4: Auditing data parity between source and target...")
    target_nodes = target_graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    target_edges = target_graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

    nodes_match = target_nodes == total_nodes
    edges_match = target_edges == total_edges

    summary = {
        "status": "success" if (nodes_match and edges_match) else "mismatch",
        "source_graph": source_graph_name,
        "target_graph": target_graph_name,
        "nodes_transferred": total_nodes,
        "target_node_count": target_nodes,
        "nodes_match": nodes_match,
        "edges_transferred": total_edges,
        "target_edge_count": target_edges,
        "edges_match": edges_match,
        "node_breakdown": node_counts_by_label,
        "edge_breakdown": edge_counts_by_type,
        "total_duration_sec": round(time.time() - t_start, 2),
    }

    if nodes_match and edges_match:
        logger.info("MIGRATION COMPLETE! 100%% Parity: %d nodes, %d edges verified.", target_nodes, target_edges)
    else:
        logger.warning("Parity Warning: Nodes (%d vs %d), Edges (%d vs %d)", total_nodes, target_nodes, total_edges, target_edges)

    return summary


def update_env_file(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    ssl: bool = False,
    instance_id: Optional[str] = None,
    graph_name: str = "tender_intel_graph",
    env_path: Optional[str] = None,
) -> bool:
    """Update .env configuration file to point all application database operations to Cloud."""
    target_file = env_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    lines: List[str] = []
    if os.path.exists(target_file):
        with open(target_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updates = {
        "FALKORDB_HOST": host,
        "FALKORDB_PORT": str(port),
        "FALKORDB_USERNAME": username or "",
        "FALKORDB_PASSWORD": password or "",
        "FALKORDB_SSL": "true" if ssl else "false",
        "FALKORDB_GRAPH_NAME": graph_name,
    }
    if instance_id:
        updates["FALKORDB_INSTANCE_ID"] = instance_id

    seen_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                seen_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in seen_keys:
            new_lines.append(f"{k}={v}\n")

    with open(target_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    logger.info("Successfully updated %s with new FalkorDB Cloud settings.", target_file)
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate local FalkorDB graph to FalkorDB Cloud.")
    parser.add_argument("--target-host", help="FalkorDB Cloud Host / Endpoint (or set FALKORDB_HOST in .env)")
    parser.add_argument("--target-port", type=int, default=None, help="FalkorDB Cloud Port (or set FALKORDB_PORT in .env)")
    parser.add_argument("--target-username", default=None, help="Cloud Username (or set FALKORDB_USERNAME in .env)")
    parser.add_argument("--target-password", default=None, help="Cloud Password (or set FALKORDB_PASSWORD in .env)")
    parser.add_argument("--target-ssl", action="store_true", default=False, help="Enable SSL/TLS for Cloud connection (default: False)")
    parser.add_argument("--no-ssl", dest="target_ssl", action="store_false", help="Disable SSL/TLS")
    parser.add_argument("--target-url", help="Direct FalkorDB connection URL (e.g. falkor://user:pass@host:port)")
    parser.add_argument("--instance-id", default=None, help="Cloud Instance ID (or set FALKORDB_INSTANCE_ID in .env)")

    parser.add_argument("--source-host", default="localhost", help="Source Host (default: localhost)")
    parser.add_argument("--source-port", type=int, default=6379, help="Source Port (default: 6379)")
    parser.add_argument("--source-graph", default="tender_intel_graph", help="Source Graph Name")
    parser.add_argument("--target-graph", default="tender_intel_graph", help="Target Graph Name")
    parser.add_argument("--clear-target", action="store_true", help="Clear target graph before importing")
    parser.add_argument("--switch-env", action="store_true", help="Update .env configuration to use Cloud database after migration")

    parser.add_argument("--allow-local-test", action="store_true", help="Allow localhost target for testing")

    args = parser.parse_args()

    settings = get_settings()
    target_host = args.target_host or settings.FALKORDB_HOST
    target_port = args.target_port or settings.FALKORDB_PORT or 6379
    target_username = args.target_username or settings.FALKORDB_USERNAME
    target_password = args.target_password or settings.FALKORDB_PASSWORD
    instance_id = args.instance_id or settings.FALKORDB_INSTANCE_ID
    target_ssl = args.target_ssl or settings.FALKORDB_SSL
    target_url = args.target_url or settings.FALKORDB_URL

    if not target_host or (target_host in ["localhost", "127.0.0.1"] and not args.allow_local_test):
        logger.error(
            "Target cloud host not specified! Configure FALKORDB_HOST in .env or pass --target-host <host>."
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("FalkorDB Docker -> Cloud Migration")
    masked_target = target_host[:6] + "***" + target_host[-8:] if len(target_host) > 20 else target_host
    logger.info("Target: %s:%d (Graph: %s, User: %s, SSL: %s)", masked_target, target_port, args.target_graph, target_username or "(anonymous)", target_ssl)
    logger.info("=" * 60)

    try:
        source_client = connect_client(host=args.source_host, port=args.source_port)
    except Exception as exc:
        logger.error("Could not connect to Source FalkorDB at %s:%d: %s", args.source_host, args.source_port, exc)
        sys.exit(1)

    try:
        target_client = connect_client(
            host=target_host,
            port=target_port,
            username=target_username,
            password=target_password,
            ssl=target_ssl,
            url=target_url,
        )
    except Exception as exc:
        logger.error("Could not connect to Target FalkorDB Cloud at %s:%d: %s", target_host, target_port, exc)
        sys.exit(1)

    res = migrate_graph(
        source_client=source_client,
        target_client=target_client,
        source_graph_name=args.source_graph,
        target_graph_name=args.target_graph,
        clear_target=args.clear_target,
    )

    print(json.dumps(res, indent=2))

    if args.switch_env and res["status"] == "success":
        update_env_file(
            host=target_host,
            port=target_port,
            username=target_username,
            password=target_password,
            ssl=target_ssl,
            instance_id=instance_id,
            graph_name=args.target_graph,
        )


if __name__ == "__main__":
    main()
