"""Comprehensive pytest verification suite for Phase 1 FalkorDB Graph & MCP Server."""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_GRAPH_NAME = "tender_intel_test_graph"
os.environ["FALKORDB_GRAPH_NAME"] = TEST_GRAPH_NAME

from db.connection import get_graph
from db.seed_graph import seed_database
from pipeline.enricher_ingestor import EnricherIngestor
from mcp_server.server import (
    get_active_tenders_and_sync_status,
    discover_direct_and_lookalike_matches,
    discover_jv_consortium_matches,
    dispatch_tender_alert_with_trace,
    record_bid_outcome_and_learn,
    execute_read_cypher,
)


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Seed the isolated test graph before running the test suite."""
    seed_res = seed_database(graph_name=TEST_GRAPH_NAME, clear_existing=True)
    assert seed_res["status"] == "success"
    yield
    # Cleanup after test suite
    try:
        graph = get_graph(TEST_GRAPH_NAME)
        graph.delete()
    except Exception:
        pass


def test_schema_and_seeding():
    """
    Test 1: Schema & Seeding Test
    Confirms all Ministries, Departments, Clients, Tenders, Brands, Products,
    Certifications, Regions, and EnlistmentClasses are created with proper node and edge properties.
    """
    graph = get_graph(TEST_GRAPH_NAME)

    # 1. Check Node Counts
    min_count = graph.query("MATCH (m:Ministry) RETURN count(m)").result_set[0][0]
    dept_count = graph.query("MATCH (d:Department) RETURN count(d)").result_set[0][0]
    client_count = graph.query("MATCH (c:Client) RETURN count(c)").result_set[0][0]
    tender_count = graph.query("MATCH (t:Tender) RETURN count(t)").result_set[0][0]
    brand_count = graph.query("MATCH (b:Brand) RETURN count(b)").result_set[0][0]
    prod_count = graph.query("MATCH (p:Product) RETURN count(p)").result_set[0][0]
    cert_count = graph.query("MATCH (c:Certification) RETURN count(c)").result_set[0][0]
    region_count = graph.query("MATCH (r:Region) RETURN count(r)").result_set[0][0]
    enlist_count = graph.query("MATCH (e:EnlistmentClass) RETURN count(e)").result_set[0][0]

    assert min_count >= 3, f"Expected at least 3 Ministries, got {min_count}"
    assert dept_count >= 4, f"Expected at least 4 Departments, got {dept_count}"
    assert client_count == 12, f"Expected 12 Clients, got {client_count}"
    assert tender_count >= 26, f"Expected at least 26 Tenders, got {tender_count}"
    assert brand_count >= 4, f"Expected at least 4 Brands, got {brand_count}"
    assert prod_count >= 4, f"Expected at least 4 Products, got {prod_count}"
    assert cert_count >= 4, f"Expected at least 4 Certifications, got {cert_count}"
    assert region_count >= 3, f"Expected at least 3 Regions, got {region_count}"
    assert enlist_count >= 3, f"Expected at least 3 EnlistmentClasses, got {enlist_count}"

    # 2. Check Client Apex Node & Edge Properties
    apex_res = graph.query("""
    MATCH (c:Client {id: 'client_apex'})-[auth:AUTHORIZED_FOR]->(b:Brand {name: 'Havells'})
    MATCH (c)-[sp:SUPPLIES]->(p:Product {name: 'LT/HT Armoured Cables'})
    MATCH (c)-[op:OPERATES_IN]->(r:Region {name: 'Karnataka'})
    RETURN c.avg_turnover_3yr, c.is_blacklisted, auth.role, auth.territory, sp.is_oem, op.gst_valid
    """).result_set[0]

    assert apex_res[0] == 120000000.0, "Apex 3-yr turnover should be 12.0 Cr"
    assert apex_res[1] is False, "Apex should not be blacklisted"
    assert apex_res[2] in ["Authorized Manufacturer", "Authorized Wholesaler", "Authorized Vendor"]
    assert apex_res[3] in ["All India", "Karnataka"]
    assert apex_res[4] is True, "Apex should be OEM supplier of LT/HT Armoured Cables"
    assert apex_res[5] is True, "Apex should have valid GST in Karnataka"

    # 3. Check Blacklisted Client Defaulter Node Property
    defaulter_res = graph.query("MATCH (c:Client {id: 'client_defaulter'}) RETURN c.is_blacklisted").result_set[0]
    assert defaulter_res[0] is True, "Defaulter Infra Corp must have is_blacklisted: True"


def test_enricher_and_sync_heartbeat():
    """
    Test 2: Enricher & Sync Heartbeat Test
    Feeds a raw scraped tender (with missing department and turnover) into EnricherIngestor,
    verifies missing fields are enriched, nodes/edges are merged into FalkorDB, and
    get_active_tenders_and_sync_status returns the updated last_scraped_at timestamp and the new tender.
    """
    ingestor = EnricherIngestor(graph_name=TEST_GRAPH_NAME)

    raw_tender = {
        "id": "T-RAW-TEST-888",
        "title": "Supply of LT/HT Armoured Cables and Havells Industrial Switchgears for Bengaluru Metro",
        "reference_no": "BMRCL/ELEC/2026/888",
        "ministry_name": "Ministry of Power",
        # department_name is missing
        "tender_amount": 40000000.0,
        # expected_turnover_3yr is missing
        "description": "Requires BIS IS-7098 certified LT/HT Armoured Cables manufactured by OEM or authorized vendor. Must have Havells authorization. Location: Karnataka.",
        "raw_location": "Bengaluru, Karnataka",
    }

    # Enrich
    enriched = ingestor.enrich_tender(raw_tender)
    assert enriched.id == "T-RAW-TEST-888"
    assert enriched.expected_turnover_3yr == 14000000.0  # 0.35 * 40M per CPWD/GeM standard
    assert enriched.min_net_worth == 4000000.0           # 0.10 * 40M
    assert enriched.min_solvency == 16000000.0          # 0.40 * 40M
    assert enriched.department_name is not None and len(enriched.department_name) > 0
    assert enriched.oem_required is True

    # Upsert into FalkorDB
    upsert_res = ingestor.upsert_tender(enriched)
    assert upsert_res["status"] == "success"
    heartbeat_ts = upsert_res["heartbeat_at"]

    # Verify via MCP tool get_active_tenders_and_sync_status
    mcp_output = json.loads(get_active_tenders_and_sync_status(graph_name=TEST_GRAPH_NAME))
    scraper_status = mcp_output["scraper_status"]

    assert scraper_status["last_scraped_at"] == heartbeat_ts
    assert scraper_status["total_tenders_ingested"] >= 7

    tender_ids = [t["id"] for t in mcp_output["tenders"]]
    assert "T-RAW-TEST-888" in tender_ids

    new_t = next(t for t in mcp_output["tenders"] if t["id"] == "T-RAW-TEST-888")
    assert new_t["expected_turnover_3yr"] == 14000000.0
    assert "Havells" in new_t["preferred_brands"]
    assert "LT/HT Armoured Cables" in new_t["required_products"]


def test_direct_and_5hop_lookalike_matching():
    """
    Test 3: Direct + 5-Hop Lookalike Matching Test
    Calls discover_direct_and_lookalike_matches on actual scraped tender IWD/IE/26-27/RT2/E-49 and asserts that:
    - Blacklisted client_defaulter is excluded.
    - client_surya (Client B) is matched AND its result explicitly cites client_apex (Client A)
      as the 5-hop lookalike peer who won past tenders.
    """
    real_tender_id = "IWD/IE/26-27/RT2/E-49"
    raw_res = discover_direct_and_lookalike_matches(real_tender_id, graph_name=TEST_GRAPH_NAME)
    res = json.loads(raw_res)

    candidates = res["candidates"]
    candidate_ids = [c["client_id"] for c in candidates]

    # Assert blacklisted client is excluded
    assert "client_defaulter" not in candidate_ids, "Blacklisted client must be strictly excluded"

    # Assert client_surya is matched
    assert "client_surya" in candidate_ids, "client_surya must be matched as a candidate"

    surya = next(c for c in candidates if c["client_id"] == "client_surya")
    assert surya["match_score"] >= 0.50, f"Expected strong match score, got {surya['match_score']}"

    # Assert 5-hop lookalike peer explicitly cites client_apex
    assert len(surya["lookalike_peers"]) > 0, "Lookalike peers should not be empty for client_surya"
    peer_ids = [p["peer_id"] for p in surya["lookalike_peers"]]
    assert "client_apex" in peer_ids, "client_apex must be cited as lookalike peer"

    apex_peer = next(p for p in surya["lookalike_peers"] if p["peer_id"] == "client_apex")
    assert apex_peer["past_tender_id"] == "CPPP/NRL/POLY/2024/01"
    assert "Wire Manufacturing Facility" in apex_peer["shared_capabilities"]
    assert "Havells" in apex_peer["shared_capabilities"]
    assert "LT/HT Armoured Cables" in apex_peer["shared_capabilities"]

    # Graph path trace verification
    assert "(:Client {id: 'client_surya'})" in surya["graph_path_trace"]
    assert "client_apex" in surya["graph_path_trace"]
    assert "CPPP/NRL/POLY/2024/01" in surya["graph_path_trace"]


def test_jv_consortium_discovery():
    """
    Test 4: JV Consortium Discovery Test
    Calls discover_jv_consortium_matches on actual scraped tender RW/NH-12014/ 04/2025-MAH/ZONE-IV and asserts that
    client_surya + client_kaveri are returned as a valid consortium covering both
    Electrical/Havells/OEM and Civil/CPWD-Class-I/Turnover requirements.
    """
    real_tender_id = "RW/NH-12014/ 04/2025-MAH/ZONE-IV"
    raw_res = discover_jv_consortium_matches(real_tender_id, graph_name=TEST_GRAPH_NAME)
    res = json.loads(raw_res)

    assert res["total_consortiums_found"] >= 1, "Expected at least 1 valid consortium"

    # Find the consortium formed by client_kaveri and client_surya
    matching_jv = None
    for jv in res["consortiums"]:
        lead_id = jv["lead_partner"]["client_id"]
        partner_id = jv["consortium_partner"]["client_id"]
        if {lead_id, partner_id} == {"client_surya", "client_kaveri"}:
            matching_jv = jv
            break

    assert matching_jv is not None, "Consortium {client_surya, client_kaveri} must be found"

    # Verify combined financials
    fin = matching_jv["combined_financials"]
    assert fin["combined_turnover"] == 315000000.0  # 22.0 Cr + 9.5 Cr = 31.5 Cr
    assert fin["combined_turnover"] >= 48000000.0  # >= 4.8 Cr requirement
    assert fin["turnover_satisfied"] is True

    # Verify complementary qualifications
    lead_nodes = matching_jv["lead_partner"]["contributed_nodes"]
    partner_nodes = matching_jv["consortium_partner"]["contributed_nodes"]

    all_wc = set(lead_nodes["work_categories"]) | set(partner_nodes["work_categories"])
    all_spec = set(lead_nodes["specializations"]) | set(partner_nodes["specializations"])
    all_brands = set(lead_nodes["brands"]) | set(partner_nodes["brands"])
    all_prods = set(lead_nodes["products"]) | set(partner_nodes["products"])
    all_enlist = set(lead_nodes["enlistment"]) | set(partner_nodes["enlistment"])

    assert "Civil Works" in all_wc and "Electrical" in all_wc, "Combined consortium must cover both Civil and Electrical"
    assert "Civil Contractor" in all_spec and "Wire Manufacturing Facility" in all_spec
    assert "Havells" in all_brands
    assert "LT/HT Armoured Cables" in all_prods
    assert "CPWD-CLASS-I-CIVIL" in all_enlist
    assert matching_jv["coverage_percentage"] == 100.0


def test_two_day_alert_cooldown_enforcement():
    """
    Test 5: 2-Day (48-Hour) Alert Cooldown Enforcement Test
    - Calls dispatch_tender_alert_with_trace for client_surya on real tender at timestamp T0 -> asserts sent is True and alert_count == 1.
    - Calls dispatch_tender_alert_with_trace again at T0 + 3600 (1 hour later) -> asserts sent is False and reason == "COOLDOWN_ACTIVE_UNDER_48H".
    - Calls discover_direct_and_lookalike_matches at T0 + 3600 -> asserts client_surya is filtered out during the active 2-day cooldown.
    - Calls dispatch_tender_alert_with_trace at T0 + 172801 (2 days + 1 second later) -> asserts sent is True and alert_count == 2.
    """
    real_tender_id = "IWD/IE/26-27/RT2/E-49"
    t0 = 1720000000

    # 1. Initial Alert Dispatch at T0
    dispatch_1 = json.loads(dispatch_tender_alert_with_trace(
        client_id="client_surya",
        tender_id=real_tender_id,
        match_score=0.88,
        match_type="DIRECT_AND_LOOKALIKE",
        reasoning_trace="Client Surya has 100% specs and lookalike peer Apex",
        path_summary="Apex -> Authority -> Surya",
        current_timestamp=t0,
        graph_name=TEST_GRAPH_NAME
    ))
    assert dispatch_1["sent"] is True
    assert dispatch_1["alert_count"] == 1
    assert dispatch_1["status"] == "ALERTED"

    # 2. Attempt Alert Dispatch at T0 + 1 Hour (3,600s) -> Must be blocked by 48h cooldown
    dispatch_2 = json.loads(dispatch_tender_alert_with_trace(
        client_id="client_surya",
        tender_id=real_tender_id,
        match_score=0.88,
        match_type="DIRECT_AND_LOOKALIKE",
        reasoning_trace="Duplicate attempt within 1 hour",
        path_summary="Apex -> Authority -> Surya",
        current_timestamp=t0 + 3600,
        graph_name=TEST_GRAPH_NAME
    ))
    assert dispatch_2["sent"] is False
    assert dispatch_2["reason"] == "COOLDOWN_ACTIVE_UNDER_48H"
    assert dispatch_2["seconds_remaining"] == 172800 - 3600

    # 3. Verify discover_direct_and_lookalike_matches filters out client_surya during active cooldown
    match_res = json.loads(discover_direct_and_lookalike_matches(
        tender_id=real_tender_id,
        current_timestamp=t0 + 3600,
        graph_name=TEST_GRAPH_NAME
    ))
    c_ids_cooldown = [c["client_id"] for c in match_res["candidates"]]
    assert "client_surya" not in c_ids_cooldown, "client_surya must be excluded from matches during active 2-day cooldown"

    # 4. Dispatch Alert at T0 + 172,801s (48 hours + 1 second) -> Cooldown expired, alert permitted
    dispatch_3 = json.loads(dispatch_tender_alert_with_trace(
        client_id="client_surya",
        tender_id=real_tender_id,
        match_score=0.88,
        match_type="DIRECT_AND_LOOKALIKE",
        reasoning_trace="Second alert after 48h cooldown expired",
        path_summary="Apex -> Authority -> Surya",
        current_timestamp=t0 + 172801,
        graph_name=TEST_GRAPH_NAME
    ))
    assert dispatch_3["sent"] is True
    assert dispatch_3["alert_count"] == 2


def test_won_lost_feedback_and_agent_learning_loop():
    """
    Test 6: Won/Lost Feedback & Agent Learning Loop Test
    - Calls record_bid_outcome_and_learn(client_id="client_surya", tender_id=real_tender_id, outcome="WON").
    - Asserts :MATCHED_TENDER.status == "WON", :BID_HISTORY.outcome == "WON", and
      :DEPARTMENT_AFFINITY between client_surya and the issuing department now exists with wins >= 1 and increased affinity_weight.
    - Asserts that even after T0 + 500000 (5+ days later), dispatch_tender_alert_with_trace does NOT re-alert because its status is terminal (WON).
    """
    real_tender_id = "IWD/IE/26-27/RT2/E-49"
    graph = get_graph(TEST_GRAPH_NAME)
    resolve_ts = 1720200000

    # Record outcome as WON
    outcome_res = json.loads(record_bid_outcome_and_learn(
        client_id="client_surya",
        tender_id=real_tender_id,
        outcome="WON",
        feedback_notes="Awarded L1 contract for cable supply",
        current_timestamp=resolve_ts,
        graph_name=TEST_GRAPH_NAME
    ))
    assert outcome_res["success"] is True
    assert outcome_res["outcome"] == "WON"

    # Verify MATCHED_TENDER and BID_HISTORY in graph
    check_query = """
    MATCH (c:Client {id: 'client_surya'})-[m:MATCHED_TENDER]->(t:Tender {id: $tender_id})
    MATCH (c)-[b:BID_HISTORY]->(t)
    RETURN m.status, m.resolved_at, b.outcome, b.feedback_notes
    """
    check_res = graph.query(check_query, {"tender_id": real_tender_id}).result_set[0]
    assert check_res[0] == "WON"
    assert check_res[1] == resolve_ts
    assert check_res[2] == "WON"
    assert check_res[3] == "Awarded L1 contract for cable supply"

    # Verify DEPARTMENT_AFFINITY between client_surya and the issuing department
    dept_query = """
    MATCH (t:Tender {id: $tender_id})<-[:ISSUED]-(d:Department)
    MATCH (c:Client {id: 'client_surya'})-[da:DEPARTMENT_AFFINITY]->(d)
    RETURN da.wins, da.losses, da.win_rate, da.affinity_weight
    """
    dept_res = graph.query(dept_query, {"tender_id": real_tender_id}).result_set[0]
    assert dept_res[0] >= 1, "Department wins should be at least 1"
    assert dept_res[1] == 0, "Department losses should be 0"
    assert dept_res[2] == 1.0, "Department win rate should be 1.0"
    assert dept_res[3] > 0.0, "Department affinity_weight should be boosted"

    # Verify that even 5+ days later (T0 + 500,000s), dispatch is blocked due to TERMINAL_STATUS
    late_ts = 1720000000 + 500000
    dispatch_late = json.loads(dispatch_tender_alert_with_trace(
        client_id="client_surya",
        tender_id=real_tender_id,
        match_score=0.95,
        match_type="DIRECT",
        reasoning_trace="Attempt to re-alert after tender was already won",
        path_summary="Authority -> Surya",
        current_timestamp=late_ts,
        graph_name=TEST_GRAPH_NAME
    ))
    assert dispatch_late["sent"] is False
    assert dispatch_late["reason"] == "TERMINAL_STATUS"
    assert dispatch_late["status"] == "WON"


def test_execute_read_cypher_diagnostic():
    """Diagnostic tool test verifying safe read execution and mutation rejection."""
    # 1. Read query works
    read_res = json.loads(execute_read_cypher(
        query="MATCH (m:Ministry) RETURN m.id AS id, m.name AS name",
        graph_name=TEST_GRAPH_NAME
    ))
    assert read_res["row_count"] >= 3

    # 2. Mutating query is blocked
    mutate_res = json.loads(execute_read_cypher(
        query="CREATE (x:BadNode {name: 'hacker'})",
        graph_name=TEST_GRAPH_NAME
    ))
    assert "error" in mutate_res
    assert "forbidden" in mutate_res["error"]
