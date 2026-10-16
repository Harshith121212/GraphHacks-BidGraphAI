"""Phase 2 Verification Suite: Strict MCP Client, Agent Loop, FastAPI Endpoints & Zero-Driver AST Tests."""

import os
import ast
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_GRAPH_NAME = "tender_intel_test_graph"
os.environ["FALKORDB_GRAPH_NAME"] = TEST_GRAPH_NAME

from db.seed_graph import seed_database
from db.connection import get_graph
from agent.mcp_agent import BidGraphMCPAgent
from api.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phase2_test_graph():
    """Ensure clean isolated test graph is seeded before running Phase 2 tests."""
    seed_res = seed_database(graph_name=TEST_GRAPH_NAME, clear_existing=True)
    assert seed_res["status"] == "success"
    yield
    try:
        g = get_graph(TEST_GRAPH_NAME)
        g.delete()
    except Exception:
        pass


def test_zero_falkordb_imports_in_agent_and_api():
    """
    Test 1: Zero-Driver AST Check
    Uses Python's ast module to parse every .py file in agent/ and api/ and
    asserts that falkordb and db modules are NEVER imported.
    Guarantees strict MCP boundary enforcement.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dirs = [os.path.join(base_dir, "agent"), os.path.join(base_dir, "api")]
    forbidden_prefixes = ("falkordb", "db", "db.connection", "db.schema", "db.seed_graph")

    inspected_files = 0
    for d in target_dirs:
        for root, _, files in os.walk(d):
            for file_name in files:
                if file_name.endswith(".py"):
                    file_path = os.path.join(root, file_name)
                    inspected_files += 1
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=file_path)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                for forbidden in forbidden_prefixes:
                                    assert not alias.name.startswith(forbidden), (
                                        f"STRICT MCP VIOLATION: '{alias.name}' imported in {file_path}. "
                                        f"Agent and API layers must not import direct graph drivers."
                                    )
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                for forbidden in forbidden_prefixes:
                                    assert not node.module.startswith(forbidden), (
                                        f"STRICT MCP VIOLATION: 'from {node.module} import ...' in {file_path}. "
                                        f"Agent and API layers must not import direct graph drivers."
                                    )

    assert inspected_files >= 4, f"Expected at least 4 files inspected in agent/ and api/, got {inspected_files}"


@pytest.mark.asyncio
async def test_mcp_client_handshake_and_tool_discovery():
    """
    Test 2: Live MCP Client Handshake & Tool Discovery
    Connects to mcp_server/server.py over stdio and verifies that all registered
    MCP tools are discovered dynamically.
    """
    agent = BidGraphMCPAgent()
    tools = await agent.list_mcp_tools()
    tool_names = [t["name"] for t in tools]

    expected_tools = [
        "get_active_tenders_and_sync_status",
        "discover_direct_and_lookalike_matches",
        "discover_jv_consortium_matches",
        "dispatch_tender_alert_with_trace",
        "record_bid_outcome_and_learn",
        "execute_read_cypher",
        "get_alerts_and_agent_memory",
        "get_graph_visualization_snapshot",
    ]

    for exp in expected_tools:
        assert exp in tool_names, f"Expected tool '{exp}' to be discovered via MCP, found: {tool_names}"

    assert len(tools) >= 8


def test_pull_tenders_button_endpoint():
    """
    Test 3: 'Pull Tender Data from DB' Endpoint
    Calls POST /api/tenders/pull via FastAPI TestClient and verifies active tenders
    and scraper sync status are returned via MCP.
    """
    response = client.post("/api/tenders/pull", json={"status_filter": "ACTIVE"})
    assert response.status_code == 200

    data = response.json()
    assert "scraper_status" in data
    assert "tenders" in data
    assert data["total_tenders"] >= 4

    # Verify trace logs MCP tool invocation
    trace = data["mcp_tool_trace"]
    assert trace["tool_name"] == "get_active_tenders_and_sync_status"
    assert trace["status"] == "success"
    assert trace["execution_time_ms"] > 0


def test_agent_matching_loop_and_48h_cooldown_via_api():
    """
    Test 4: End-to-End Agent Matching Loop & 48-Hour Cooldown Enforcement via API
    - Runs matching loop at T0 = 1760000000.
    - Asserts alerts dispatched for IWD/IE/26-27/RT2/E-49 (client_surya with 5-hop lookalike trace from client_apex)
      and RW/NH-12014/ 04/2025-MAH/ZONE-IV (JV Consortium client_kaveri + client_surya).
    - Calls matching loop again at T0 + 3600 (1 hour later): verifies alerts_dispatched == 0
      and alerts_skipped_cooldown_or_terminal > 0 due to 2-day cooldown.
    - Calls matching loop at T0 + 172810 (2 days + 10 seconds later): verifies alerts are re-sent.
    """
    t0 = 1760000000
    real_lookalike_tender = "IWD/IE/26-27/RT2/E-49"
    real_jv_tender = "RW/NH-12014/ 04/2025-MAH/ZONE-IV"

    # 1. First run of the Matching Loop at T0
    res1 = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t0,
    })
    assert res1.status_code == 200
    data1 = res1.json()

    assert data1["tenders_evaluated"] >= 4
    assert data1["alerts_dispatched"] >= 2
    assert data1["direct_or_lookalike_matches_found"] >= 1
    assert data1["jv_consortiums_found"] >= 1

    # Check client_surya decision on real tender
    surya_decisions = [
        d for d in data1["decisions"]
        if d["client_id"] == "client_surya" and d["tender_id"] == real_lookalike_tender
    ]
    assert len(surya_decisions) >= 1
    surya_d = surya_decisions[0]
    assert surya_d["action"] == "ALERT_SENT"
    assert "client_apex" in surya_d["reasoning_trace"], "Reasoning trace must cite lookalike peer client_apex"

    # Check JV consortium decision for real JV tender
    jv_decisions = [
        d for d in data1["decisions"]
        if d["tender_id"] == real_jv_tender and d["match_type"] == "JV_CONSORTIUM"
    ]
    assert len(jv_decisions) >= 1
    jv_d = jv_decisions[0]
    assert jv_d["action"] == "ALERT_SENT"
    assert "JOINT VENTURE" in jv_d["reasoning_trace"]
    assert "Combined Financials" in jv_d["reasoning_trace"]

    # 2. Second run of the Matching Loop at T0 + 1 Hour (3,600s) -> Active 48h Cooldown
    res2 = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t0 + 3600,
    })
    assert res2.status_code == 200
    data2 = res2.json()

    assert data2["alerts_dispatched"] == 0, "No new alerts should be dispatched within 48-hour cooldown window"
    assert data2["alerts_skipped_cooldown_or_terminal"] > 0, "Alerts should be skipped due to active cooldown"

    # 3. Third run of the Matching Loop at T0 + 172,810s (48 hours + 10 seconds) -> Cooldown Expired
    res3 = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t0 + 172810,
    })
    assert res3.status_code == 200
    data3 = res3.json()

    assert data3["alerts_dispatched"] > 0, "Alerts should be re-dispatched after 48h cooldown has elapsed"


def test_won_lost_buttons_update_affinity_and_halt_alerts_via_api():
    """
    Test 5: 'Won' / 'Lost' Outcome Buttons, Graph Learning Loop & Terminal Status Halting
    - Calls POST /api/alerts/outcome with outcome='WON' for client_surya on real tender.
    - Calls GET /api/dashboard and verifies alert status is 'WON' and learned affinity weight increased.
    - Calls subsequent POST /api/agent/match calls even 10 days later (T0 + 1,000,000s)
      and verifies client_surya is NEVER re-alerted because status is terminal (WON).
    """
    real_tender_id = "IWD/IE/26-27/RT2/E-49"
    t0 = 1760000000
    resolve_ts = t0 + 200000

    # 1. Record Outcome as WON
    outcome_res = client.post("/api/alerts/outcome", json={
        "client_id": "client_surya",
        "tender_id": real_tender_id,
        "outcome": "WON",
        "feedback_notes": "Lowest bid confirmed, contract signed",
        "current_timestamp": resolve_ts,
    })
    assert outcome_res.status_code == 200
    outcome_data = outcome_res.json()
    assert outcome_data["success"] is True
    assert outcome_data["outcome"] == "WON"

    # Verify Department Affinity updated
    dept_aff = outcome_data["department_affinity"]
    assert dept_aff is not None
    assert dept_aff["wins"] >= 1
    assert dept_aff["win_rate"] == 1.0
    assert dept_aff["affinity_weight"] > 0.0

    # 2. Verify Dashboard State reflects WON status and updated affinities
    dash_res = client.get(f"/api/dashboard?client_id=client_surya&current_timestamp={resolve_ts}")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()

    # Find the alert for the real tender
    surya_alerts = [a for a in dash_data["alerts"] if a["tender_id"] == real_tender_id]
    assert len(surya_alerts) >= 1
    assert surya_alerts[0]["status"] == "WON"
    assert surya_alerts[0]["cooldown_active"] is False

    # Check learned affinities list in dashboard
    surya_dept_affs = [
        aff for aff in dash_data["learned_affinities"]
        if aff["client_id"] == "client_surya"
    ]
    assert len(surya_dept_affs) >= 1
    assert surya_dept_affs[0]["wins"] >= 1
    assert surya_dept_affs[0]["affinity_weight"] > 0.0

    # 3. Trigger matching loop 10 days later (T0 + 1,000,000s) -> Terminal state must prevent re-alerting
    late_ts = t0 + 1000000
    late_match_res = client.post("/api/agent/match", json={
        "tender_ids": [real_tender_id],
        "min_score_threshold": 0.50,
        "current_timestamp": late_ts,
    })
    assert late_match_res.status_code == 200
    late_data = late_match_res.json()

    # Verify client_surya was NEVER sent an alert
    surya_late_sent = [
        d for d in late_data["decisions"]
        if d["client_id"] == "client_surya" and d["tender_id"] == real_tender_id and d["action"] == "ALERT_SENT"
    ]
    assert len(surya_late_sent) == 0, "Terminal status tender (WON) must never be re-alerted!"
