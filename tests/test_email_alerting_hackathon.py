"""
Comprehensive Test Suite for Hackathon Email Alerting Requirements:
1. All client nodes in FalkorDB maintain email = 'hackathon-demo@outlook.com'.
2. Sending a single alert via POST /api/agent/send-alert dispatches to hackathon-demo@outlook.com.
3. Alert email payload contains:
   - client name
   - tender name
   - tender value (formatted)
   - plus points of client
   - reason why client was chosen
4. Strict Competitor Privacy Shield: In hop/lookalike matches, the anchor/peer competitor identity
   (name, client ID, past contract ID, turnover threshold) is NEVER revealed.
5. Batch alert dispatch via POST /api/agent/send-all-alerts dispatches alerts for all active matches
   to hackathon-demo@outlook.com.
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from api.main import app
from agent.communication_agent import CommunicationAgent
from db.connection import get_graph
from db.seed_graph import seed_database

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_email_tests():
    """Ensure baseline graph nodes are present for email alerting tests."""
    seed_database(graph_name="tender_intel_graph", clear_existing=False)
    yield


def test_all_clients_have_hackathon_demo_email():
    """Verify all clients in the FalkorDB graph have email set to hackathon-demo@outlook.com."""
    graph = get_graph("tender_intel_graph")
    res = graph.query("MATCH (c:Client) RETURN c.id, c.name, c.email").result_set
    assert len(res) >= 12, "Expected at least 12 clients in graph"
    for r in res:
        cid, cname, email = r[0], r[1], r[2]
        assert email == "hackathon-demo@outlook.com", f"Client {cid} ({cname}) email is {email}, expected 'hackathon-demo@outlook.com'"


def test_send_single_alert_endpoint_payload():
    """
    Test POST /api/agent/send-alert:
    Must include client name, tender name, tender value, plus points, and reason chosen.
    Recipient must be hackathon-demo@outlook.com.
    """
    res = client.post("/api/agent/send-alert", json={
        "client_id": "client_surya",
        "tender_id": "GEM/2026/B/8059713"
    })
    assert res.status_code == 200, f"Error: {res.text}"
    data = res.json()
    assert data["success"] is True
    assert data["recipient"] == "hackathon-demo@outlook.com"

    record = data["record"]
    assert record["client_name"] == "Surya Wire & Switchgear Pvt Ltd"
    assert record["client_email"] == "hackathon-demo@outlook.com"
    assert record["dispatched_to"] == "hackathon-demo@outlook.com"
    assert record["tender_id"] == "GEM/2026/B/8059713"
    assert record["tender_name"] != ""
    assert "₹" in record["tender_value_formatted"]
    assert len(record["plus_points"]) > 0
    assert record["reason_chosen"] is not None and len(record["reason_chosen"]) > 10

    # Verify presence in plain body
    body = record["body_plain"]
    assert "Surya Wire & Switchgear Pvt Ltd" in body
    assert record["tender_value_formatted"] in body or "Lakhs" in body or "Crores" in body
    assert "hackathon-demo@outlook.com" in body


def test_lookalike_privacy_shield_never_reveals_peer():
    """
    Privacy Shield Assertion:
    If a client is chosen because of hop/lookalike, never reveal the other client
    because of which this client was matched.
    """
    comm_agent = CommunicationAgent()

    # Raw trace with peer company details that could potentially leak
    raw_trace_with_peer_leak = (
        "1. AI GRAPH-HOPPING MULTI-HOP DISCOVERY:\n"
        "2. ANCHOR MATCH: Discovered lookalike match for Surya Wire & Switchgear Pvt Ltd (client_surya)\n"
        "   based on peer competitor Apex Electricals & Cables Ltd (client_apex) who won past contract CPPP/NRL/POLY/2024/01 with turnover ₹12.00 Cr.\n"
        "3. Shared capabilities: Wire Manufacturing Facility, Havells authorization.\n"
        "4. DECISIVE WINNING PLUS POINTS FOR SURYA WIRE & SWITCHGEAR PVT LTD:\n"
        "   • High liquidity turnover ₹9.50 Cr.\n"
        "   • Verified statutory compliance.\n"
    )

    # 1. Test Privacy Shield Sanitizer
    sanitized = comm_agent._sanitize_privacy_shield(raw_trace_with_peer_leak, "client_surya")

    assert "Apex Electricals" not in sanitized, "Peer competitor full name must not appear in output"
    assert "Apex" not in sanitized, "Peer competitor name must not appear in output"
    assert "client_apex" not in sanitized, "Peer client ID must not appear in output"
    assert "CPPP/NRL/POLY/2024/01" not in sanitized, "Peer past contract ID must not appear in output"
    assert "12.00 Cr" not in sanitized, "Peer turnover benchmark must not appear in output"

    # 2. Test Reason Chosen generator for lookalike hop
    reason = comm_agent._determine_reason_chosen(
        match_type="LOOKALIKE_PEER",
        client_name="Surya Wire & Switchgear Pvt Ltd",
        tender_title="LT/HT Cables Substation Package",
        tender_info={"department": "NTPC Karnataka Region"},
        client_info={"id": "client_surya"},
        reasoning_trace=raw_trace_with_peer_leak
    )
    assert "5-hop lookalike capability analysis" in reason
    assert "Surya Wire & Switchgear Pvt Ltd" in reason
    assert "Apex" not in reason, "Peer competitor must not be named in reason"
    assert "client_apex" not in reason, "Peer client ID must not appear in reason"
    assert "peer identities" in reason.lower() or "lookalike" in reason.lower()


def test_batch_alert_send_endpoint():
    """
    Test POST /api/agent/send-all-alerts:
    Dispatches alerts for all active tender matches to hackathon-demo@outlook.com.
    """
    from db.connection import get_graph
    graph = get_graph()
    graph.query("""
    MATCH (c:Client {id: 'client_bharat_it'}), (t:Tender {id: 'GEM/2026/R/751080'})
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.status = 'ALERTED',
        m.match_score = 0.94,
        m.last_alert_sent = 1700000000
    """)

    res = client.post("/api/agent/send-all-alerts")
    assert res.status_code == 200, f"Batch send error: {res.text}"
    data = res.json()
    assert data["total_sent"] >= 1
    assert data["recipient"] == "hackathon-demo@outlook.com"
    assert len(data["records"]) == data["total_sent"]

    # Check that outbox file data/dispatched_alerts.jsonl was written
    outbox_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dispatched_alerts.jsonl")
    assert os.path.exists(outbox_file), "Outbox log file should exist"
    with open(outbox_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) >= data["total_sent"]
    assert any(l["recipient"] == "hackathon-demo@outlook.com" for l in lines)
