"""
Test Phase 5: Communication Agent & NVIDIA Nemotron-3.5 Alert Email Engine
Tests:
1. AST isolation verification: CommunicationAgent does not import FalkorDB directly.
2. Model verification: model_id strictly set to nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4.
3. Client email resolution from FalkorDB c.email attribute (None -> PENDING_CLIENT_NODE_UPDATE, set -> CONFIGURED).
4. Content completeness: Drafted email cites tender name, scope of work, tender value, plus points, and end date.
5. FastAPI endpoint POST /api/agent/draft-email.
6. FastAPI endpoint POST /api/agent/draft-all-emails.
"""

import ast
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_GRAPH_NAME = "tender_intel_test_graph"

from agent.communication_agent import CommunicationAgent
from api.main import app
from db.connection import get_graph
from db.seed_graph import seed_database

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phase5_test_graph():
    """Ensure clean isolated test graph is seeded and matched before running Phase 5 tests."""
    old_graph = os.environ.get("FALKORDB_GRAPH_NAME", "tender_intel_graph")
    os.environ["FALKORDB_GRAPH_NAME"] = TEST_GRAPH_NAME
    seed_res = seed_database(graph_name=TEST_GRAPH_NAME, clear_existing=True)
    assert seed_res["status"] == "success"
    # Run matching loop to generate alerts and decisions
    res = client.post("/api/agent/match", json={"current_timestamp": 1720000000})
    assert res.status_code == 200
    try:
        yield
    finally:
        try:
            g = get_graph(TEST_GRAPH_NAME)
            g.delete()
        except Exception:
            pass
        os.environ["FALKORDB_GRAPH_NAME"] = old_graph


def test_zero_direct_db_imports_in_communication_agent():
    """
    AST Isolation Test: Ensure communication_agent.py communicates strictly via MCP
    and contains ZERO direct imports of falkordb or internal db.* packages.
    """
    file_path = os.path.join(os.path.dirname(__file__), "..", "agent", "communication_agent.py")
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)

    forbidden_modules = ["falkordb", "db", "db.client", "db.schema"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in forbidden_modules:
                    assert not alias.name.startswith(forbidden), f"Forbidden import '{alias.name}' in communication_agent.py"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for forbidden in forbidden_modules:
                    assert not node.module.startswith(forbidden), f"Forbidden import-from '{node.module}' in communication_agent.py"


def test_communication_agent_model_target():
    """
    Verify Communication Agent strictly targets nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4.
    """
    agent = CommunicationAgent()
    assert agent.model_id == "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"


@pytest.mark.asyncio
async def test_email_draft_with_unconfigured_and_configured_client_email():
    """
    Verify that when c.email is None, the email status is PENDING_CLIENT_NODE_UPDATE
    and when c.email is set, the email status is CONFIGURED and recipient email is populated.
    """
    agent = CommunicationAgent()
    graph = get_graph()

    # Ensure client_bharat_it has a matched alert on GEM/2026/R/751080
    graph.query("""
    MATCH (c:Client {id: 'client_bharat_it'})
    MERGE (t:Tender {id: 'GEM/2026/R/751080'})
    ON CREATE SET t.title = 'Supply, Installation & Maintenance of Server Infrastructure and IT Hardware',
                  t.tender_amount = 12500000.0,
                  t.deadline_at = 1750000000,
                  t.source_portal = 'GeM',
                  t.status = 'ACTIVE',
                  t.listed_date = '2026-10-12'
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.status = 'ALERTED', m.match_score = 0.94, m.last_alert_sent = 1700000000
    MERGE (ad:AgentDecision {id: 'dec_seed_bharat_it'})
    SET ad.action = 'ALERT_SENT', ad.match_score = 0.94, ad.match_type = 'DIRECT'
    MERGE (ad)-[:FOR_CLIENT]->(c)
    MERGE (ad)-[:EVALUATED_TENDER]->(t)
    """)

    test_client = "client_bharat_it"
    tender_id = "GEM/2026/R/751080"

    # Step A: Ensure client has email = None initially
    graph.query("MATCH (c:Client {id: $cid}) REMOVE c.email", {"cid": test_client})

    draft_unconf = await agent.draft_alert_email(test_client, tender_id)
    assert draft_unconf is not None
    assert draft_unconf.client_email is None
    assert draft_unconf.email_status == "PENDING_CLIENT_NODE_UPDATE"
    assert "Pending on Client Node" in draft_unconf.email_body
    assert draft_unconf.tender_title != ""
    assert "₹" in draft_unconf.tender_value_formatted
    assert draft_unconf.tender_deadline != ""
    assert len(draft_unconf.plus_points) > 0

    # Step B: Set client email dynamically in FalkorDB
    test_email = "bidding-desk@bharat-digital.in"
    graph.query("MATCH (c:Client {id: $cid}) SET c.email = $email", {"cid": test_client, "email": test_email})

    try:
        draft_conf = await agent.draft_alert_email(test_client, tender_id)
        assert draft_conf is not None
        assert draft_conf.client_email == test_email
        assert draft_conf.email_status == "CONFIGURED"
        assert test_email in draft_conf.email_body
        assert draft_conf.model_used == "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
    finally:
        # Cleanup: reset c.email back to demo email
        graph.query("MATCH (c:Client {id: $cid}) SET c.email = 'hackathon-demo@outlook.com'", {"cid": test_client})


def test_api_draft_email_endpoint():
    """
    Test POST /api/agent/draft-email endpoint.
    """
    graph = get_graph()
    graph.query("""
    MATCH (c:Client {id: 'client_bharat_it'})
    MERGE (t:Tender {id: 'GEM/2026/R/751080'})
    ON CREATE SET t.title = 'Supply, Installation & Maintenance of Server Infrastructure and IT Hardware',
                  t.tender_amount = 12500000.0,
                  t.deadline_at = 1750000000,
                  t.source_portal = 'GeM',
                  t.status = 'ACTIVE',
                  t.listed_date = '2026-10-12'
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.status = 'ALERTED', m.match_score = 0.94, m.last_alert_sent = 1700000000
    MERGE (ad:AgentDecision {id: 'dec_seed_bharat_it'})
    SET ad.action = 'ALERT_SENT', ad.match_score = 0.94, ad.match_type = 'DIRECT'
    MERGE (ad)-[:FOR_CLIENT]->(c)
    MERGE (ad)-[:EVALUATED_TENDER]->(t)
    """)

    test_client = "client_bharat_it"
    tender_id = "GEM/2026/R/751080"

    response = client.post("/api/agent/draft-email", json={
        "client_id": test_client,
        "tender_id": tender_id
    })
    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == test_client
    assert data["tender_id"] == tender_id
    assert "tender_title" in data
    assert "tender_value_formatted" in data
    assert "tender_deadline" in data
    assert "fit_score_pct" in data
    assert "scope_of_work" in data
    assert "plus_points" in data
    assert len(data["plus_points"]) > 0
    assert data["model_used"] == "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"


def test_api_draft_all_emails_endpoint():
    """
    Test POST /api/agent/draft-all-emails endpoint.
    """
    graph = get_graph()
    graph.query("""
    MATCH (c:Client {id: 'client_bharat_it'})
    MERGE (t:Tender {id: 'GEM/2026/R/751080'})
    ON CREATE SET t.title = 'Supply, Installation & Maintenance of Server Infrastructure and IT Hardware',
                  t.tender_amount = 12500000.0,
                  t.deadline_at = 1750000000,
                  t.source_portal = 'GeM',
                  t.status = 'ACTIVE',
                  t.listed_date = '2026-10-12'
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.status = 'ALERTED', m.match_score = 0.94, m.last_alert_sent = 1700000000
    MERGE (ad:AgentDecision {id: 'dec_seed_bharat_it'})
    SET ad.action = 'ALERT_SENT', ad.match_score = 0.94, ad.match_type = 'DIRECT'
    MERGE (ad)-[:FOR_CLIENT]->(c)
    MERGE (ad)-[:EVALUATED_TENDER]->(t)
    """)

    response = client.post("/api/agent/draft-all-emails")
    assert response.status_code == 200
    data = response.json()
    assert "total_drafted" in data
    assert data["total_drafted"] >= 1
    assert "drafts" in data
    assert len(data["drafts"]) == data["total_drafted"]
    first_draft = data["drafts"][0]
    assert first_draft["model_used"] == "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"


def test_peer_email_redacts_anchor_identity_and_contracts():
    """
    Privacy Shield Test: Verifies that when drafting an alert email for lookalike peer client_surya,
    the competitor anchor's corporate name ('Apex Electricals', 'client_apex'), turnover ('12.00 Cr', '120000000'),
    and contract reference ('CPPP/NRL/POLY/2024/01') are strictly redacted by code at the tool/agent layer.
    """
    agent = CommunicationAgent()
    # Test with simulated reasoning trace containing raw anchor details
    mock_trace = (
        "• Financial Liquidity: 3-Year turnover ₹9.50 Cr satisfies MSME requirements.\n"
        "• 5-Hop Lookalike Benchmark: Client client_apex (Apex Electricals & Cables Ltd) won contract CPPP/NRL/POLY/2024/01 with turnover ₹12.00 Cr.\n"
        "• Accredited Quality Standards: Holds BIS IS-7098."
    )
    client_data = {"id": "client_surya", "name": "Surya Wire & Switchgear Pvt Ltd", "turnover_3yr": 95000000.0, "is_msme": True}
    pts = agent._extract_plus_points_from_trace(mock_trace, client_data)
    sanitized_pts = [agent._sanitize_privacy_shield(p, "client_surya") for p in pts]
    combined_text = " ".join(sanitized_pts)

    assert "Apex Electricals" not in combined_text, "Anchor name must be redacted"
    assert "client_apex" not in combined_text, "Anchor ID must be redacted"
    assert "CPPP/NRL/POLY/2024/01" not in combined_text, "Anchor contract ID must be redacted"
    assert "12.00 Cr" not in combined_text, "Anchor turnover must be redacted"
    assert "120000000" not in combined_text, "Anchor numeric turnover must be redacted"

