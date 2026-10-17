"""Phase 4 Verification Suite: JV Consortium Hub, 5-Stage Decision Tree, LangGraph Agent & Zero-Driver AST."""

import os
import sys
import ast
import json
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.seed_graph import seed_database
from db.connection import get_graph
from api.main import app

TEST_GRAPH_NAME = "tender_intel_test_graph"
os.environ["FALKORDB_GRAPH_NAME"] = TEST_GRAPH_NAME

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phase4_test_graph():
    """Ensure clean isolated test graph is seeded before running Phase 4 tests."""
    seed_res = seed_database(graph_name=TEST_GRAPH_NAME, clear_existing=True)
    assert seed_res["status"] == "success"
    yield
    try:
        g = get_graph(TEST_GRAPH_NAME)
        g.delete()
    except Exception:
        pass
    finally:
        os.environ["FALKORDB_GRAPH_NAME"] = "tender_intel_graph"


def test_phase4_preserves_strict_zero_driver_ast_isolation():
    """Asserts that neither agent/ nor api/ imports falkordb or direct db drivers."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dirs = [os.path.join(base_dir, "agent"), os.path.join(base_dir, "api")]
    forbidden = ("falkordb", "db", "db.connection", "db.schema", "db.seed_graph")

    inspected = 0
    for d in target_dirs:
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".py"):
                    inspected += 1
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8") as pyfile:
                        tree = ast.parse(pyfile.read(), filename=path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                for forb in forbidden:
                                    assert not alias.name.startswith(forb), f"AST violation in {path}: {alias.name}"
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                for forb in forbidden:
                                    assert not node.module.startswith(forb), f"AST violation in {path}: {node.module}"

    assert inspected >= 5, f"Expected at least 5 files inspected, got {inspected}"


def test_tender_estimated_values_populated_and_positive():
    """Verifies that tender estimated value and turnover fields are non-zero positive floats."""
    res = client.post("/api/tenders/pull", json={"status_filter": "ACTIVE"})
    assert res.status_code == 200
    data = res.json()
    tenders = data["tenders"]
    assert len(tenders) >= 5

    for t in tenders:
        est_val = t.get("estimated_value_inr") or t.get("tender_amount") or 0.0
        turnover = t.get("min_avg_turnover") or t.get("expected_turnover_3yr") or 0.0
        assert est_val > 0.0, f"Tender {t.get('id')} has zero estimated value"
        assert turnover > 0.0, f"Tender {t.get('id')} has zero required turnover"


def test_jv_consortium_graph_persistence_and_decision_tree():
    """
    Verifies that discover_jv_consortium_matches persists :JVConsortium node
    in FalkorDB with a complete 5-stage decision tree.
    """
    real_tender_id = "RW/NH-12014/ 04/2025-MAH/ZONE-IV"
    match_res = client.post("/api/agent/match", json={
        "tender_ids": [real_tender_id],
        "min_score_threshold": 0.40,
        "current_timestamp": 1720000000,
    })
    assert match_res.status_code == 200

    dash_res = client.get("/api/dashboard?current_timestamp=1720000000")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()

    jvs = dash_data.get("jv_consortiums", [])
    assert len(jvs) >= 1, "Expected at least 1 JV consortium in dashboard"

    target_jv = next((j for j in jvs if "RW/NH-12014" in j["tender_id"]), None)
    assert target_jv is not None, "Target JV consortium for NH-848 tender must exist"

    dt = target_jv.get("decision_tree", {})
    assert "stage1_solo_disqualification" in dt
    assert "stage2_financial_aggregation" in dt
    assert "stage3_capability_union" in dt
    assert "stage4_regional_compliance" in dt
    assert "stage5_governance_recommendation" in dt

    assert dt["stage1_solo_disqualification"]["gate_passed"] is True
    assert dt["stage2_financial_aggregation"]["gate_passed"] is True
    assert dt["stage3_capability_union"]["coverage_percentage"] == 100.0


def test_jv_outcome_learning_loop():
    """Verifies that POST /api/jv/outcome updates JV status and PARTNERSHIP_AFFINITY in FalkorDB."""
    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    jvs = dash_res.json().get("jv_consortiums", [])
    assert len(jvs) >= 1

    jv_id = jvs[0]["id"]

    res = client.post("/api/jv/outcome", json={
        "jv_id": jv_id,
        "outcome": "WON",
        "current_timestamp": 1720500000,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "WON"
    assert data["wins"] >= 1
    assert data["affinity_score"] >= 0.90


def test_langgraph_agentic_workflow_execution():
    """Verifies the multi-node LangGraph StateGraph pipeline execution."""
    res = client.post("/api/agent/langgraph/run", json={
        "min_score_threshold": 0.40,
        "current_timestamp": 1720600000,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["tenders_evaluated"] >= 1
    assert data["executed_at"] == 1720600000
    assert len(data["mcp_tool_calls"]) > 0
