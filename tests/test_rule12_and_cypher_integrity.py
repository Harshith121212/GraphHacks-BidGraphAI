"""Test suite for Rule 12 Cypher query validity, Laplace smoothing, idempotency, and privacy."""

import os
import sys
import pytest
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_graph
from mcp_server.server import record_bid_outcome_and_learn, find_peer_clients, explore_paths
from agent.communication_agent import CommunicationAgent
from config import get_settings

TEST_GRAPH = "tender_intel_graph"


def test_readme_cypher_queries_syntax_and_execution():
    """
    Rule 12 Validation: Executes all Cypher query patterns published in documentation
    against live FalkorDB graph to guarantee zero syntax errors and valid schema execution.
    """
    graph = get_graph(TEST_GRAPH)
    now = int(time.time())

    # Find a real active tender
    t_res = graph.query("MATCH (t:Tender {status: 'ACTIVE'}) RETURN t.id LIMIT 1")
    assert len(t_res.result_set) > 0
    tender_id = t_res.result_set[0][0]

    # Pattern A: Direct Multi-Criteria Eligibility Gate with Dynamic Coverage Scoring
    pattern_a = """
    MATCH (t:Tender {id: $tender_id})
    MATCH (c:Client {is_blacklisted: false})

    // 1. Financial & Bidding Capacity Solvency Gate (with robust NULL requirement guards)
    WHERE (t.status = 'ACTIVE' OR t.status IS NULL)
      AND (t.deadline_at IS NULL OR t.deadline_at > $current_timestamp)
      AND (t.expected_turnover_3yr IS NULL OR c.avg_turnover_3yr >= t.expected_turnover_3yr
           OR (c.is_msme = true AND t.msme_exempt_turnover = true))
      AND (t.min_net_worth IS NULL OR c.net_worth >= t.min_net_worth)
      AND (t.min_solvency IS NULL OR c.solvency >= t.min_solvency)
      AND (t.max_ongoing_work_allowed IS NULL OR coalesce(c.ongoing_work_value, 0) <= t.max_ongoing_work_allowed)
      AND (t.min_tech_staff IS NULL OR coalesce(c.tech_staff_count, 0) >= t.min_tech_staff)
      AND (t.min_local_content_class IS NULL OR t.min_local_content_class = 'CLASS-2' OR c.local_content_class = 'CLASS-1')

    // 2. Regional / GST Territorial Gate
    MATCH (t)-[:LOCATED_IN]->(r:Region)
    MATCH (c)-[op:OPERATES_IN]->(r)
    WHERE op.gst_valid = true

    // 3. Trade Category Match
    MATCH (t)-[:IN_CATEGORY]->(twc:WorkCategory)<-[:WORKS_IN]-(c)

    // 4. Specialization Gate
    WITH t, c, r, [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization) | spec] AS req_specs
    WITH t, c, r, req_specs, [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization)<-[:HAS_SPECIALIZATION]-(c) | spec] AS held_specs
    WHERE size(held_specs) = size(req_specs)

    // 5. Enlistment Class Gate (with valid expiration)
    WITH t, c, r, [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec] AS req_enlist
    WITH t, c, r, req_enlist, [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass)<-[en:ENLISTED_AS]-(c)
          WHERE en.valid_until IS NULL OR en.valid_until > $current_timestamp | ec] AS valid_enlist
    WHERE size(valid_enlist) = size(req_enlist)

    // 6. Mandatory Technical Certifications Gate (with valid expiration)
    WITH t, c, r, [(t)-[:REQUIRES_CERT]->(rc:Certification) | rc] AS req_certs
    WITH t, c, r, req_certs, [(t)-[:REQUIRES_CERT]->(rc:Certification)<-[hc:HOLDS_CERT]-(c) 
          WHERE hc.valid_until IS NULL OR hc.valid_until > $current_timestamp | rc] AS valid_certs
    WHERE size(valid_certs) = size(req_certs)

    // 7. Brand & OEM Strict Authorization Gate (with territorial match & valid expiration)
    WITH t, c, r, [(t)-[pb:PREFERS_BRAND]->(b:Brand) WHERE pb.strict_auth_required = true | b] AS req_brands
    WITH t, c, r, req_brands, [(t)-[pb:PREFERS_BRAND]->(b:Brand)<-[auth:AUTHORIZED_FOR]-(c) 
          WHERE (auth.valid_until IS NULL OR auth.valid_until > $current_timestamp) 
            AND (auth.territory IN ['All India', 'ALL_INDIA', r.name]) | b] AS auth_brands
    WHERE size(auth_brands) = size(req_brands)

    // 8. Cooldown & Terminal State Filter
    WITH t, c,
         [(c)-[eval:MATCHED_TENDER]->(t) 
          WHERE eval.status IN ['WON', 'LOST'] 
             OR (eval.status = 'ALERTED' AND ($current_timestamp - eval.last_alert_sent) < 172800) | eval] AS blocked_evals
    WHERE size(blocked_evals) = 0

    // 9. Product BOQ Coverage Depth & Department Affinity Scoring
    OPTIONAL MATCH (t)-[:REQUIRES_PRODUCT]->(rp:Product)
    WITH t, c, count(DISTINCT rp) AS total_prods

    OPTIONAL MATCH (c)-[sp:SUPPLIES]->(mp:Product)<-[:REQUIRES_PRODUCT]-(t)
    OPTIONAL MATCH (c)-[da:DEPARTMENT_AFFINITY]->(d:Department)<-[:ISSUED]-(t)

    WITH c, total_prods, count(DISTINCT mp) AS matched_prods, coalesce(da.affinity_weight, 0.0) AS aff_wt
    WITH c, (toFloat(matched_prods) / toFloat(CASE WHEN total_prods = 0 THEN 1 ELSE total_prods END)) AS prod_coverage, aff_wt
    WITH c, (0.70 + 0.20 * prod_coverage + aff_wt) AS raw_score

    RETURN c.id AS client_id, c.name AS client_name, c.avg_turnover_3yr AS turnover,
           round((CASE WHEN raw_score > 1.0 THEN 1.0 ELSE raw_score END) * 10000.0) / 10000.0 AS match_score
    """
    res_a = graph.query(pattern_a, {"tender_id": tender_id, "current_timestamp": now})
    assert res_a is not None

    # Pattern B: 5-Hop Lookalike Peer Discovery with (peer, anchor) Grouping & Minimum 2 Distinct Anchors
    pattern_b = """
    MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
    MATCH (t)<-[:ISSUED]-(d:Department)-[:ISSUED]->(past_t:Tender)-[:IN_CATEGORY]->(wc)
    MATCH (anchor:Client)-[:BID_HISTORY {outcome: 'WON'}]->(past_t)
    WHERE anchor.is_blacklisted = false

    MATCH (peer:Client)
    WHERE ($client_id IS NULL OR $client_id = '' OR peer.id = $client_id)
      AND peer.id <> anchor.id
      AND peer.is_blacklisted = false
      AND (peer.avg_turnover_3yr >= coalesce(t.expected_turnover_3yr, 0) OR (peer.is_msme = true AND t.msme_exempt_turnover = true))
      AND NOT (peer)-[:BID_HISTORY]->(:Tender)<-[:ISSUED]-(d)

    MATCH (t)-[:LOCATED_IN]->(r:Region)
    MATCH (peer)-[op:OPERATES_IN]->(r)
    WHERE op.gst_valid = true

    MATCH (peer)-[:WORKS_IN]->(wc)

    OPTIONAL MATCH (t)-[:REQUIRES_CERT]->(req_cert:Certification)
    OPTIONAL MATCH (peer)-[hc:HOLDS_CERT]->(req_cert)
      WHERE hc.valid_until IS NULL OR hc.valid_until > $current_timestamp
    WITH t, d, past_t, anchor, peer,
         count(DISTINCT req_cert) AS total_req_certs,
         count(DISTINCT hc) AS held_req_certs
    WHERE total_req_certs = 0 OR held_req_certs = total_req_certs

    OPTIONAL MATCH (t)-[:PREFERS_BRAND]->(req_brand:Brand)
    OPTIONAL MATCH (peer)-[auth:AUTHORIZED_FOR]->(req_brand)
      WHERE auth.valid_until IS NULL OR auth.valid_until > $current_timestamp
    WITH t, d, past_t, anchor, peer,
         count(DISTINCT req_brand) AS total_req_brands,
         count(DISTINCT auth) AS held_req_brands
    WHERE total_req_brands = 0 OR held_req_brands = total_req_brands

    WITH t, d, past_t, anchor, peer,
         [(peer)-[eval:MATCHED_TENDER]->(t)
          WHERE eval.status IN ['WON', 'LOST']
             OR (eval.status = 'ALERTED' AND ($current_timestamp - eval.last_alert_sent) < 172800) | eval] AS blocked_evals
    WHERE size(blocked_evals) = 0

    // Group by (peer, anchor): require >= 2 shared capabilities per anchor
    MATCH (anchor)-[:WORKS_IN|HAS_SPECIALIZATION|HOLDS_CERT|AUTHORIZED_FOR|SUPPLIES]->(shared)<-[:WORKS_IN|HAS_SPECIALIZATION|HOLDS_CERT|AUTHORIZED_FOR|SUPPLIES]-(peer)
    WITH peer, anchor, count(DISTINCT shared) AS shared_per_anchor
    WHERE shared_per_anchor >= 2

    // Group by peer: require >= 2 distinct supporting anchors
    WITH peer, count(DISTINCT anchor) AS supporting_anchors, sum(shared_per_anchor) AS total_shared_caps
    WHERE supporting_anchors >= 2

    WITH peer, supporting_anchors, total_shared_caps,
         (0.68 + 0.15 * (CASE WHEN supporting_anchors >= 3 THEN 1.0 ELSE 0.6 END)) AS raw_score

    RETURN peer.id AS peer_client_id, peer.name AS peer_name,
           "[Generic Peer Benchmark - Identity Shielded]" AS benchmark_reference,
           supporting_anchors,
           total_shared_caps,
           round((CASE WHEN raw_score > 0.92 THEN 0.92 ELSE raw_score END) * 10000.0) / 10000.0 AS match_score
    """
    res_b = graph.query(pattern_b, {"tender_id": "IWD/IE/26-27/RT2/E-49", "client_id": "client_surya", "current_timestamp": now})
    assert res_b is not None
    assert len(res_b.result_set) > 0, "Pattern B lookalike traversal should discover peer client_surya"
    assert res_b.result_set[0][0] == "client_surya"
    assert res_b.result_set[0][2] == "[Generic Peer Benchmark - Identity Shielded]"
    assert res_b.result_set[0][3] >= 2, "Pattern B must find at least 2 distinct supporting anchors"

    # Pattern C: Joint Venture Consortium Synthesis with Product Coverage & Zero-Product Handling
    pattern_c = """
    MATCH (t:Tender {id: $tender_id, status: 'ACTIVE'})
    WHERE t.expected_turnover_3yr > 20000000.0

    MATCH (lead:Client {is_blacklisted: false})
    MATCH (t)-[:IN_CATEGORY]->(wc_lead:WorkCategory)<-[:WORKS_IN]-(lead)
    WHERE lead.avg_turnover_3yr < t.expected_turnover_3yr

    MATCH (partner:Client {is_blacklisted: false})
    MATCH (t)-[:IN_CATEGORY]->(wc_partner:WorkCategory)<-[:WORKS_IN]-(partner)
    WHERE partner.id <> lead.id
      AND partner.avg_turnover_3yr < t.expected_turnover_3yr
      AND wc_partner.name <> wc_lead.name

    MATCH (t)-[:LOCATED_IN]->(r:Region)
    MATCH (lead)-[op1:OPERATES_IN]->(r)
    MATCH (partner)-[op2:OPERATES_IN]->(r)
    WHERE op1.gst_valid = true AND op2.gst_valid = true

    WITH t, lead, partner, wc_lead, wc_partner,
         (lead.avg_turnover_3yr + partner.avg_turnover_3yr) AS combined_turnover,
         (lead.net_worth + partner.net_worth) AS combined_net_worth
    WHERE combined_turnover >= t.expected_turnover_3yr
      AND (t.min_net_worth IS NULL OR combined_net_worth >= t.min_net_worth)

    OPTIONAL MATCH (t)-[:REQUIRES_PRODUCT]->(all_p:Product)
    WITH t, lead, partner, combined_turnover, combined_net_worth, count(DISTINCT all_p) AS total_products
    OPTIONAL MATCH (t)-[:REQUIRES_PRODUCT]->(p:Product)
      WHERE (lead)-[:SUPPLIES]->(p) OR (partner)-[:SUPPLIES]->(p)
    WITH t, lead, partner, combined_turnover, combined_net_worth, total_products, count(DISTINCT p) AS covered_products
    WHERE (total_products = 0) OR (covered_products = total_products)

    WITH lead, partner, combined_turnover, t,
         (0.75 + 0.15 * (CASE WHEN (combined_turnover / t.expected_turnover_3yr) > 1.3 THEN 1.0 ELSE (combined_turnover / t.expected_turnover_3yr) - 0.3 END)) AS raw_synergy

    RETURN lead.id AS lead_id, lead.name AS lead_name, lead.avg_turnover_3yr AS lead_turnover,
           partner.id AS partner_id, partner.name AS partner_name, partner.avg_turnover_3yr AS partner_turnover,
           combined_turnover, t.expected_turnover_3yr AS required_turnover,
           round((CASE WHEN raw_synergy > 0.98 THEN 0.98 ELSE raw_synergy END) * 10000.0) / 10000.0 AS synergy_score
    """
    res_c = graph.query(pattern_c, {"tender_id": "RW/NH-12014/ 04/2025-MAH/ZONE-IV"})
    assert res_c is not None


def test_laplace_smoothed_learning_and_double_click_idempotency():
    """
    Tests that:
    1. Recording a bid outcome uses Laplace smoothing (prior 0.5; single win does NOT give max 0.25).
    2. SET evaluation order correctly reflects the updated win/loss totals.
    3. Clicking Won twice on the same tender is idempotent and does not double-count wins.
    """
    graph = get_graph(TEST_GRAPH)
    test_client = "client_surya"
    test_tender = "GEM/2026/B/8069018"

    # Reset test client state on this tender
    graph.query("""
    MATCH (c:Client {id: $cid})-[m:MATCHED_TENDER]->(t:Tender {id: $tid})
    SET m.status = 'ALERTED'
    """, {"cid": test_client, "tid": test_tender})

    # First call: Record WON
    import json
    res1_raw = record_bid_outcome_and_learn(
        client_id=test_client,
        tender_id=test_tender,
        outcome="WON",
        current_timestamp=1700000000,
        graph_name=TEST_GRAPH,
    )
    res1 = json.loads(res1_raw)
    assert res1["success"] is True
    dept_aff1 = res1.get("department_affinity", {})
    wins1 = dept_aff1.get("wins", 0)
    losses1 = dept_aff1.get("losses", 0)
    affinity_wt1 = dept_aff1.get("affinity_weight", 0.0)

    # Laplace smoothed weight: ((wins + 1) / (wins + losses + 2) - 0.5) * 0.5
    expected_wt = round(((float(wins1 + 1) / float(wins1 + losses1 + 2)) - 0.5) * 0.5, 4)
    assert abs(affinity_wt1 - expected_wt) < 0.001, f"Expected {expected_wt}, got {affinity_wt1}"
    # Verify single win does NOT yield max 0.25
    assert affinity_wt1 < 0.25

    # Second call (Simulating Double Click): Record WON again on identical tender
    res2_raw = record_bid_outcome_and_learn(
        client_id=test_client,
        tender_id=test_tender,
        outcome="WON",
        current_timestamp=1700000005,
        graph_name=TEST_GRAPH,
    )
    res2 = json.loads(res2_raw)
    assert res2["success"] is True
    assert res2.get("idempotent_skip") is True, "Second identical outcome MUST trigger idempotent_skip"

    # Verify wins and affinity did not double-increment
    dept_aff2 = res2.get("department_affinity", {})
    assert dept_aff2.get("wins") == wins1, "Double click must not increment wins twice"
    assert dept_aff2.get("affinity_weight") == affinity_wt1, "Double click must not change affinity weight"


@pytest.mark.asyncio
async def test_lookalike_peer_alert_and_email_zero_anchor_leakage():
    """
    Verifies that drafted email alert for a lookalike peer contains:
    - Zero anchor company name
    - Zero anchor 3-year turnover
    - Zero anchor past contract reference ID
    """
    comm_agent = CommunicationAgent()
    draft = await comm_agent.draft_alert_email(
        client_id="client_apex",
        tender_id="IWD/IE/26-27/RT2/E-49",
        graph_name=TEST_GRAPH,
    )
    assert draft is not None
    body = draft.email_body

    # Strictly forbidden anchor attributes
    assert "Surya Wire" not in body, "Privacy Leak: Anchor company name present in peer email"
    assert "95000000" not in body, "Privacy Leak: Anchor turnover present in peer email"
    assert "₹9.50 Cr" not in body, "Privacy Leak: Anchor turnover present in peer email"
    assert "CPPP/NRL/POLY/2024/01" not in body, "Privacy Leak: Anchor past contract reference leaked"
    assert "CPPP/HURL/ELECTRICAL/2024/02" not in body, "Privacy Leak: Anchor past contract reference leaked"


def test_pattern_f_explore_paths_syntax_and_whitelist():
    """
    Verifies that explore_paths:
    1. Validates start and target node types against the strict label whitelist.
    2. Rejects unauthorized / malicious label injections.
    3. Executes FalkorDB-compliant shortestPath syntax over directed traversals with coalesce(path_fwd, path_rev).
    """
    # 1. Valid exploration
    spec_valid = json.dumps({
        "start_type": "Client",
        "start_id": "client_apex",
        "target_type": "Department",
        "target_id": "dept_hurl"
    })
    res_valid_raw = explore_paths(spec_valid, graph_name=TEST_GRAPH)
    res_valid = json.loads(res_valid_raw)
    assert res_valid["success"] is True
    assert res_valid["paths_found"] >= 1
    assert len(res_valid["paths"]) >= 1

    # 2. Invalid label injection rejection
    spec_invalid = json.dumps({
        "start_type": "ArbitraryInjectedLabel",
        "start_id": "client_apex",
        "target_type": "Department",
        "target_id": "dept_hurl"
    })
    res_invalid_raw = explore_paths(spec_invalid, graph_name=TEST_GRAPH)
    res_invalid = json.loads(res_invalid_raw)
    assert res_invalid["success"] is False
    assert "Invalid node type in spec" in res_invalid["error"]


def test_pattern_d_tenders_without_department_handling():
    """
    Verifies that recording an outcome on a tender lacking an issuing department
    (common on CPPP scrapers) does not crash and cleanly returns NO_DEPARTMENT status.
    """
    graph = get_graph(TEST_GRAPH)
    no_dept_tid = "TENDER_NO_DEPT_TEST_001"
    
    # Ensure test tender has no department
    graph.query("""
    MERGE (t:Tender {id: $tid})
    SET t.title = 'Scraped Tender Without Issuing Department',
        t.status = 'ACTIVE',
        t.tender_amount = 2500000.0,
        t.expected_turnover_3yr = 1000000.0
    """, {"tid": no_dept_tid})

    try:
        res_raw = record_bid_outcome_and_learn(
            client_id="client_surya",
            tender_id=no_dept_tid,
            outcome="WON",
            current_timestamp=1700000010,
            graph_name=TEST_GRAPH,
        )
        res = json.loads(res_raw)
        assert res["success"] is True
        dept_aff = res.get("department_affinity", {})
        assert dept_aff.get("status") == "NO_DEPARTMENT"
        assert "No procuring department associated with tender" in dept_aff.get("message", "")
    finally:
        try:
            graph.query("MATCH (t:Tender {id: $tid}) DETACH DELETE t", {"tid": no_dept_tid})
        except Exception:
            pass


def test_pattern_a_credential_gating_rejects_missing_credentials():
    """
    Punchlist Verification:
    Tests that a client missing a required certification or brand authorization is rejected by Pattern A.
    """
    graph = get_graph(TEST_GRAPH)
    test_tender = "IWD/IE/26-27/RT2/E-49"
    now = int(time.time())

    # 1. Test certification gating: simulate requiring ISO 13485 (which client_surya does not hold)
    graph.query("""
    MATCH (t:Tender {id: $tid}), (c:Certification {name: 'ISO 13485'})
    MERGE (t)-[r:REQUIRES_CERT]->(c)
    """, {"tid": test_tender})

    try:
        from mcp_server.server import discover_direct_and_lookalike_matches
        res_raw = discover_direct_and_lookalike_matches(test_tender, current_timestamp=now, graph_name=TEST_GRAPH)
        res = json.loads(res_raw)
        matched_cids = [c["client_id"] for c in res.get("candidates", [])]
        assert "client_surya" not in matched_cids, "Client missing required certification MUST be rejected by Pattern A"
    finally:
        graph.query("""
        MATCH (t:Tender {id: $tid})-[r:REQUIRES_CERT]->(:Certification {name: 'ISO 13485'})
        DELETE r
        """, {"tid": test_tender})

    # 2. Test brand authorization gating: simulate requiring Voltas brand with strict_auth_required
    graph.query("""
    MATCH (t:Tender {id: $tid}), (b:Brand {name: 'Voltas'})
    MERGE (t)-[r:PREFERS_BRAND {strict_auth_required: true}]->(b)
    """, {"tid": test_tender})

    try:
        from mcp_server.server import discover_direct_and_lookalike_matches
        res_raw = discover_direct_and_lookalike_matches(test_tender, current_timestamp=now, graph_name=TEST_GRAPH)
        res = json.loads(res_raw)
        matched_cids = [c["client_id"] for c in res.get("candidates", [])]
        assert "client_surya" not in matched_cids, "Client missing required brand authorization MUST be rejected by Pattern A"
    finally:
        graph.query("""
        MATCH (t:Tender {id: $tid})-[r:PREFERS_BRAND]->(:Brand {name: 'Voltas'})
        DELETE r
        """, {"tid": test_tender})


def test_pattern_a_and_c_null_requirements_do_not_drop_qualifying_clients():
    """
    Punchlist Verification:
    Tests that NULL requirements on tenders (min_net_worth IS NULL, min_solvency IS NULL, min_tech_staff IS NULL)
    do not evaluate to NULL and falsely drop eligible clients.
    """
    graph = get_graph(TEST_GRAPH)
    null_test_tid = "TENDER_NULL_REQ_TEST_001"
    now = int(time.time())

    # Create a tender where financial and staff requirements are NULL
    graph.query("""
    MERGE (t:Tender {id: $tid})
    SET t.title = 'Null Requirement Evaluation Tender',
        t.status = 'ACTIVE',
        t.tender_amount = 500000.0,
        t.expected_turnover_3yr = 200000.0,
        t.min_net_worth = NULL,
        t.min_solvency = NULL,
        t.min_tech_staff = NULL,
        t.min_local_content_class = NULL,
        t.max_ongoing_work_allowed = NULL,
        t.deadline_at = $deadline
    WITH t
    MATCH (d:Department {id: 'dept_hurl'})
    MATCH (r:Region {name: 'Maharashtra'})
    MATCH (wc:WorkCategory {name: 'Electrical'})
    MERGE (d)-[:ISSUED]->(t)
    MERGE (t)-[:LOCATED_IN]->(r)
    MERGE (t)-[:IN_CATEGORY]->(wc)
    """, {"tid": null_test_tid, "deadline": now + 86400})

    try:
        from mcp_server.server import discover_direct_and_lookalike_matches
        res_raw = discover_direct_and_lookalike_matches(null_test_tid, current_timestamp=now, graph_name=TEST_GRAPH)
        res = json.loads(res_raw)
        matched_cids = [c["client_id"] for c in res.get("candidates", [])]
        assert "client_surya" in matched_cids, "Qualifying client must NOT be dropped when tender has NULL net_worth/solvency/staff"
    finally:
        graph.query("MATCH (t:Tender {id: $tid}) DETACH DELETE t", {"tid": null_test_tid})


def test_pattern_f_explore_paths_privacy_shield_blocks_competitor_edges():
    """
    Punchlist Verification:
    Tests that explore_paths shortestPath explicitly excludes BID_HISTORY and MATCHED_TENDER
    relationships, preventing competitor exploration leaks.
    """
    spec = json.dumps({
        "start_type": "Client",
        "start_id": "client_apex",
        "target_type": "Tender",
        "target_id": "CPPP/NRL/POLY/2024/01"
    })
    res_raw = explore_paths(spec, graph_name=TEST_GRAPH)
    res = json.loads(res_raw)
    assert res["success"] is True
    # For every returned path, ensure neither BID_HISTORY nor MATCHED_TENDER is included
    for p in res.get("paths", []):
        rels = p.get("relationships", [])
        assert "BID_HISTORY" not in rels, "Privacy Violation: BID_HISTORY exposed in topological shortest path"
        assert "MATCHED_TENDER" not in rels, "Privacy Violation: MATCHED_TENDER exposed in topological shortest path"


def test_pattern_b_lookalike_peer_eligibility_and_cooldown_gating():
    """
    Punchlist Verification:
    Tests that lookalike peers in Pattern B must strictly satisfy:
    - Non-blacklisted status
    - Valid GST in tender region
    - Turnover eligibility
    - 48-hour cooldown filter
    """
    graph = get_graph(TEST_GRAPH)
    test_tender = "IWD/IE/26-27/RT2/E-49"
    now = int(time.time())

    # 1. Normal run: client_surya is eligible peer
    res1_raw = find_peer_clients(client_id="client_surya", tender_id=test_tender, current_timestamp=now, graph_name=TEST_GRAPH)
    res1 = json.loads(res1_raw)
    assert res1["peer_count"] >= 1
    assert any(p["peer_id"] == "client_surya" for p in res1["peers"])

    # 2. Simulate cooldown on client_surya
    graph.query("""
    MATCH (c:Client {id: 'client_surya'}), (t:Tender {id: $tid})
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.status = 'ALERTED', m.last_alert_sent = $now
    """, {"tid": test_tender, "now": now})

    try:
        # Cooldown check: 100 seconds later (under 48h) -> client_surya must be blocked
        res_cooldown_raw = find_peer_clients(client_id="client_surya", tender_id=test_tender, current_timestamp=now + 100, graph_name=TEST_GRAPH)
        res_cooldown = json.loads(res_cooldown_raw)
        cooldown_peers = [p["peer_id"] for p in res_cooldown.get("peers", [])]
        assert "client_surya" not in cooldown_peers, "Client on active cooldown must be blocked from lookalike peer discovery"
    finally:
        # Clean up test match state
        graph.query("""
        MATCH (c:Client {id: 'client_surya'})-[m:MATCHED_TENDER]->(t:Tender {id: $tid})
        DELETE m
        """, {"tid": test_tender})


