"""Phase 3 Verification Suite: UI Serving, Complete E2E Judge Workflow & Zero-Driver AST Check."""

import os
import ast
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_GRAPH_NAME = "tender_intel_test_graph"

from db.seed_graph import seed_database
from db.connection import get_graph
from api.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phase3_test_graph():
    """Ensure clean isolated test graph is seeded before running Phase 3 tests."""
    old_graph = os.environ.get("FALKORDB_GRAPH_NAME", "tender_intel_graph")
    os.environ["FALKORDB_GRAPH_NAME"] = TEST_GRAPH_NAME
    seed_res = seed_database(graph_name=TEST_GRAPH_NAME, clear_existing=True)
    assert seed_res["status"] == "success"
    try:
        yield
    finally:
        try:
            g = get_graph(TEST_GRAPH_NAME)
            g.delete()
        except Exception:
            pass
        os.environ["FALKORDB_GRAPH_NAME"] = old_graph


def test_frontend_ui_served_and_assets_load():
    """
    Test 1: FastAPI Static Frontend Serving
    Verifies that the single-port FastAPI app serves the executive dashboard HTML,
    custom dark-glassmorphism stylesheet, and D3 controller script with 200 OK.
    """
    # 1. Test GET / (HTML Dashboard)
    res_index = client.get("/")
    assert res_index.status_code == 200
    html_content = res_index.text
    assert "BidGraphAI" in html_content
    assert 'id="graph-canvas"' in html_content
    assert 'id="alert-feed-container"' in html_content
    assert 'id="affinity-panel"' in html_content
    assert 'id="mcp-audit-log"' in html_content
    assert 'id="btn-pull-tenders"' in html_content
    assert 'id="btn-run-match"' in html_content
    assert 'id="btn-time-jump"' in html_content
    assert 'id="btn-reset-demo"' in html_content

    # 2. Test GET /styles.css
    res_css = client.get("/styles.css")
    assert res_css.status_code == 200
    css_content = res_css.text
    assert ".glass-card" in css_content
    assert ".graph-node" in css_content

    # 3. Test GET /app.js
    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    js_content = res_js.text
    assert "fetchDashboard" in js_content
    assert "handlePullTenders" in js_content
    assert "handleRunMatchingLoop" in js_content
    assert "handleTimeJump" in js_content
    assert "d3.forceSimulation" in js_content


def test_reset_and_seed_demo_via_mcp_endpoint():
    """
    Test 2: One-Click Demo Reset via MCP
    Calls POST /api/demo/reset and verifies the graph is restored to the benchmark state
    strictly through the FastMCP server with ZERO direct db imports.
    """
    res = client.post("/api/demo/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["benchmark_tenders_seeded"] >= 4
    assert data["benchmark_clients_seeded"] >= 4
    assert data["graph_name"] == TEST_GRAPH_NAME


def test_enrich_and_ingest_new_tender_via_api_and_pull():
    """
    Test 3: LLM Tender Enrichment & Ingestion via API & Pull
    Submits a new raw tender payload through POST /api/pipeline/enrich-and-ingest,
    then verifies it appears in FalkorDB when calling POST /api/tenders/pull.
    """
    new_tender_payload = {
        "tender_id": "T-2026-999-PHASE3",
        "title": "Turnkey Solar-Wind Hybrid Power Plant Ingestion Test",
        "department": "Solar Energy Corporation of India (SECI)",
        "ministry": "Ministry of New and Renewable Energy",
        "estimated_value_inr": 75000000.0,
        "min_avg_turnover": 30000000.0,
        "work_category": "Renewable Power EPC",
        "required_certifications": ["ISO-9001", "CEA-GRID-COMPLIANCE"],
        "required_oem_brands": ["ABB", "Siemens"],
        "location": "Karnataka",
    }

    # 1. Ingest via API
    ingest_res = client.post("/api/pipeline/enrich-and-ingest", json=new_tender_payload)
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.json()
    assert ingest_data["tender_id"] == "T-2026-999-PHASE3"
    assert ingest_data["status"] in ["success", "INGESTED"]

    # 2. Verify tender is pulled from FalkorDB via MCP
    pull_res = client.post("/api/tenders/pull", json={"status_filter": "ACTIVE"})
    assert pull_res.status_code == 200
    pull_data = pull_res.json()
    assert pull_data["total_tenders"] >= 5

    pulled_ids = [t["tender_id"] for t in pull_data["tenders"]]
    assert "T-2026-999-PHASE3" in pulled_ids


def test_full_e2e_judge_demo_flow_with_time_jump_and_learning():
    """
    Test 4: Full E2E Judge Demo Journey
    Step A: Reset benchmark demo graph.
    Step B: Pull active tenders from FalkorDB.
    Step C: Run matching loop at T0 (alerts dispatched).
    Step D: Run matching loop at T0 + 10 min (blocked by 48h cooldown).
    Step E: Record 'WON' feedback for client_surya on T-2026-001 (updates affinity).
    Step F: Advance simulated time by +48h (T0 + 172,810s).
            Run matching loop again:
            - Expired cooldown pairs ARE re-alerted.
            - Terminal status pair (client_surya on T-2026-001) is NEVER re-alerted!
    Step G: Verify Dashboard state (telemetry, topology snapshot, learned affinities).
    """
    # Step A: Reset Graph
    reset_res = client.post("/api/demo/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["success"] is True

    # Step B: Pull active tenders
    pull_res = client.post("/api/tenders/pull", json={"status_filter": "ACTIVE"})
    assert pull_res.status_code == 200
    tenders = pull_res.json()["tenders"]
    assert len(tenders) >= 4

    # Step C: Matching loop at T0 = 1710000000
    t0 = 1710000000
    match1_res = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t0,
    })
    assert match1_res.status_code == 200
    match1 = match1_res.json()
    assert match1["alerts_dispatched"] >= 4

    # Step D: Matching loop at T0 + 600s (10 min later) -> 48h Cooldown Blocks Re-Alert
    match2_res = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t0 + 600,
    })
    assert match2_res.status_code == 200
    match2 = match2_res.json()
    assert match2["alerts_dispatched"] == 0
    assert match2["alerts_skipped_cooldown_or_terminal"] > 0

    # Step E: Record WON outcome on real tender for client_surya
    real_tender_id = "IWD/IE/26-27/RT2/E-49"
    outcome_res = client.post("/api/alerts/outcome", json={
        "client_id": "client_surya",
        "tender_id": real_tender_id,
        "outcome": "WON",
        "feedback_notes": "Lowest L1 commercial bid and compliant OEM authorization confirmed.",
        "current_timestamp": t0 + 1200,
    })
    assert outcome_res.status_code == 200
    outcome_data = outcome_res.json()
    assert outcome_data["success"] is True
    assert outcome_data["outcome"] == "WON"
    assert outcome_data["department_affinity"]["wins"] >= 1
    assert outcome_data["department_affinity"]["affinity_weight"] > 0.0

    # Step F: Advance simulated time by +48h (T0 + 172,810s)
    t_after_48h = t0 + 172810
    match3_res = client.post("/api/agent/match", json={
        "min_score_threshold": 0.50,
        "current_timestamp": t_after_48h,
    })
    assert match3_res.status_code == 200
    match3 = match3_res.json()

    # Re-alerts should be dispatched for eligible non-terminal pairs whose cooldown expired
    assert match3["alerts_dispatched"] > 0

    # The WON pair (client_surya on real tender) must NEVER receive an alert
    surya_won_alert = [
        d for d in match3["decisions"]
        if d["client_id"] == "client_surya" and d["tender_id"] == real_tender_id and d["action"] == "ALERT_SENT"
    ]
    assert len(surya_won_alert) == 0, "Terminal tender (WON) must never be re-alerted!"

    # Step G: Verify Dashboard State
    dash_res = client.get(f"/api/dashboard?current_timestamp={t_after_48h}")
    assert dash_res.status_code == 200
    dash = dash_res.json()

    # Verify Graph Snapshot
    assert len(dash["graph_snapshot"]["nodes"]) >= 10
    assert len(dash["graph_snapshot"]["links"]) >= 10

    # Verify Learned Affinities
    surya_affs = [
        a for a in dash["learned_affinities"]
        if a["client_id"] == "client_surya" and a["wins"] >= 1
    ]
    assert len(surya_affs) >= 1
    assert surya_affs[0]["win_rate"] == 1.0


def test_phase3_preserves_zero_driver_ast_isolation():
    """
    Test 5: AST Zero-Driver Isolation
    Verifies that across all code in agent/ and api/, zero direct falkordb or db.* imports exist.
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
