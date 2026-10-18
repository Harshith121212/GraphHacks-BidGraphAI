"""FastMCP Server exposing specialized FalkorDB graph intelligence tools."""

import os
import sys
import time
import json
import uuid
import logging
import re
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from config import get_settings
from db.connection import get_graph

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("tender-intelligence-mcp")


def _get_target_graph(graph_name: Optional[str] = None):
    settings = get_settings()
    target = graph_name or os.environ.get("FALKORDB_GRAPH_NAME", settings.FALKORDB_GRAPH_NAME)
    return get_graph(target)


def _read_only_query_error(query: str) -> Optional[str]:
    """Conservatively validate diagnostic Cypher before it reaches FalkorDB.

    These endpoints are for read-only investigation. Core product operations use
    dedicated parameterized MCP templates instead of accepting arbitrary Cypher.
    """
    scrubbed = re.sub(r"/\*[\s\S]*?\*/", " ", query)
    scrubbed = re.sub(r"//[^\n]*", " ", scrubbed)
    scrubbed = re.sub(r"'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"", " ", scrubbed)
    normalized = scrubbed.strip()
    if not normalized:
        return "Cypher query is empty."
    if normalized.count(";") > 1 or (";" in normalized and not normalized.endswith(";")):
        return "Multiple Cypher statements are not allowed."
    if not re.match(r"^(MATCH|OPTIONAL\s+MATCH)\b", normalized, flags=re.IGNORECASE):
        return "Read-only diagnostic queries must begin with MATCH or OPTIONAL MATCH."
    forbidden = re.search(
        r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL|LOAD|FOREACH)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if forbidden:
        return f"Operation '{forbidden.group(1).upper()}' is not allowed in read-only Cypher diagnostics."
    return None


@mcp.tool()
def get_active_tenders_and_sync_status(
    status_filter: str = "ACTIVE",
    graph_name: Optional[str] = None
) -> str:
    """
    Queries SystemMeta scraper status and fetches all tenders matching status_filter along with
    their connected Ministry, Department, Region, WorkCategory, Specialization, Certification,
    Brand, Product, and EnlistmentClass nodes.
    """
    graph = _get_target_graph(graph_name)

    # 1. Fetch Scraper Status
    meta_res = graph.query("""
    MATCH (sm:SystemMeta {key: 'scraper_status'})
    RETURN sm.last_scraped_at AS last_scraped_at,
           sm.total_tenders_ingested AS total_tenders_ingested,
           sm.scraper_source AS scraper_source
    """)
    scraper_status = {}
    if meta_res.result_set:
        row = meta_res.result_set[0]
        scraper_status = {
            "last_scraped_at": row[0],
            "total_tenders_ingested": row[1],
            "scraper_source": row[2],
        }

    # 2. Fetch Tenders
    tenders_query = """
    MATCH (t:Tender)
    WHERE $status_filter = 'ALL' OR t.status = $status_filter
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    OPTIONAL MATCH (m:Ministry)-[:HAS_DEPARTMENT]->(d)
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(r:Region)
    RETURN t.id AS id,
           t.title AS title,
           t.reference_no AS reference_no,
           t.tender_amount AS tender_amount,
           t.expected_turnover_3yr AS expected_turnover_3yr,
           t.min_net_worth AS min_net_worth,
           t.min_solvency AS min_solvency,
           t.max_ongoing_work_allowed AS max_ongoing_work_allowed,
           t.oem_required AS oem_required,
           t.min_local_content_class AS min_local_content_class,
           t.min_tech_staff AS min_tech_staff,
           t.msme_exempt_turnover AS msme_exempt_turnover,
           t.status AS status,
           t.published_at AS published_at,
           t.deadline_at AS deadline_at,
           d.id AS department_id,
           d.name AS department_name,
           m.id AS ministry_id,
           m.name AS ministry_name,
           r.name AS region_name,
           r.state_code AS region_state_code,
           [(t)-[:IN_CATEGORY]->(wc:WorkCategory) | wc.name] AS work_categories,
           [(t)-[:REQUIRES_SPECIALIZATION]->(s:Specialization) | s.name] AS specializations,
           [(t)-[:REQUIRES_CERT]->(c:Certification) | c.name] AS certifications,
           [(t)-[:PREFERS_BRAND]->(b:Brand) | b.name] AS preferred_brands,
           [(t)-[:REQUIRES_PRODUCT]->(p:Product) | p.name] AS required_products,
           [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec.code] AS enlistment_classes,
           t.scraped_at AS scraped_at,
           t.source_portal AS source_portal,
           t.listed_date AS listed_date,
           t.tender_url AS tender_url
    """
    res = graph.query(tenders_query, {"status_filter": status_filter})
    tenders = []
    seen_ids = set()
    from datetime import datetime, date
    now_dt = datetime.now().astimezone()
    for r in res.result_set:
        if r[0] in seen_ids:
            continue
        seen_ids.add(r[0])
        scraped_val = r[27] if len(r) > 27 and r[27] else now_dt.isoformat()
        portal_val = r[28] if len(r) > 28 and r[28] else ("GeM" if str(r[0]).startswith("GEM") else "CPPP")
        listed_val = r[29] if len(r) > 29 and r[29] else now_dt.strftime("%Y-%m-%d")
        url_val = r[30] if len(r) > 30 and r[30] else None

        tenders.append({
            "id": r[0],
            "tender_id": r[0],
            "title": r[1],
            "reference_no": r[2],
            "tender_amount": r[3],
            "estimated_value_inr": r[3],
            "expected_turnover_3yr": r[4],
            "min_avg_turnover": r[4],
            "min_net_worth": r[5],
            "min_solvency": r[6],
            "max_ongoing_work_allowed": r[7],
            "oem_required": r[8],
            "min_local_content_class": r[9],
            "min_tech_staff": r[10],
            "msme_exempt_turnover": r[11],
            "status": r[12],
            "published_at": r[13],
            "deadline_at": r[14],
            "department": {"id": r[15], "name": r[16]},
            "department_name": r[16],
            "ministry": {"id": r[17], "name": r[18]},
            "region": {"name": r[19], "state_code": r[20]},
            "location": r[19],
            "work_categories": r[21],
            "work_category": r[21][0] if r[21] else "General",
            "specializations": r[22],
            "certifications": r[23],
            "preferred_brands": r[24],
            "required_products": r[25],
            "enlistment_classes": r[26],
            "scraped_at": scraped_val,
            "source_portal": portal_val,
            "listed_date": listed_val,
            "tender_url": url_val,
        })

    payload = {
        "scraper_status": scraper_status,
        "total_tenders": len(tenders),
        "tenders": tenders,
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def discover_direct_and_lookalike_matches(
    tender_id: str,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Finds ranked eligible clients for a tender using native OpenCypher traversals.
    Executes hard financial/MSME filtering, 2-day cooldown enforcement, multi-hop capability verification,
    5-hop lookalike peer discovery (Client A -> Client B), and learned agent memory affinity boosts.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())

    # 1. Fetch Tender Requirements
    t_info_query = """
    MATCH (t:Tender {id: $tender_id})-[:LOCATED_IN]->(r:Region)
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    RETURN t.id AS id,
           t.title AS title,
           d.id AS dept_id,
           d.name AS dept_name,
           r.name AS region_name,
           t.expected_turnover_3yr AS expected_turnover,
           t.oem_required AS oem_required,
           [(t)-[:IN_CATEGORY]->(twc:WorkCategory) | twc.name] AS req_wc,
           [(t)-[:REQUIRES_SPECIALIZATION]->(tspec:Specialization) | tspec.name] AS req_spec,
           [(t)-[:REQUIRES_CERT]->(tcert:Certification) | tcert.name] AS req_cert,
           [(t)-[:PREFERS_BRAND]->(tb:Brand) | tb.name] AS req_brands,
           [(t)-[:REQUIRES_PRODUCT]->(tp:Product) | tp.name] AS req_prods,
           [(t)-[:REQUIRES_ENLISTMENT]->(tec:EnlistmentClass) | tec.code] AS req_enlist
    """
    t_res = graph.query(t_info_query, {"tender_id": tender_id})
    if not t_res.result_set:
        return json.dumps({"error": f"Tender {tender_id} not found", "candidates": []})

    t_row = t_res.result_set[0]
    tender_meta = {
        "id": t_row[0],
        "title": t_row[1],
        "dept_id": t_row[2],
        "dept_name": t_row[3],
        "region_name": t_row[4],
        "expected_turnover": t_row[5],
        "oem_required": t_row[6],
        "req_wc": set(t_row[7]),
        "req_spec": set(t_row[8]),
        "req_cert": set(t_row[9]),
        "req_brands": set(t_row[10]),
        "req_prods": set(t_row[11]),
        "req_enlist": set(t_row[12]),
    }

    # Total distinct requirements for capability scoring
    total_req_count = (
        len(tender_meta["req_wc"]) +
        len(tender_meta["req_spec"]) +
        len(tender_meta["req_cert"]) +
        len(tender_meta["req_brands"]) +
        len(tender_meta["req_prods"]) +
        len(tender_meta["req_enlist"])
    )
    if total_req_count == 0:
        total_req_count = 1

    # 2. Hard Eligibility Filter + 2-Day Cooldown Check + Multi-Hop Credential Gating
    candidates_query = """
    MATCH (t:Tender {id: $tender_id})-[:LOCATED_IN]->(r:Region)
    MATCH (d:Department)-[:ISSUED]->(t)
    MATCH (c:Client)-[op:OPERATES_IN]->(r)
    WHERE (t.status = 'ACTIVE' OR t.status IS NULL)
      AND (t.deadline_at IS NULL OR t.deadline_at > $now)
      AND c.is_blacklisted = false
      AND op.gst_valid = true
      AND (t.expected_turnover_3yr IS NULL OR c.avg_turnover_3yr >= t.expected_turnover_3yr OR (c.is_msme = true AND t.msme_exempt_turnover = true))
      AND (t.min_net_worth IS NULL OR c.net_worth >= t.min_net_worth)
      AND (t.min_solvency IS NULL OR c.solvency >= t.min_solvency)
      AND (t.max_ongoing_work_allowed IS NULL OR coalesce(c.ongoing_work_value, 0) <= t.max_ongoing_work_allowed)
      AND (t.min_tech_staff IS NULL OR c.tech_staff_count >= t.min_tech_staff)
      AND (t.min_local_content_class IS NULL OR t.min_local_content_class = 'CLASS-2' OR c.local_content_class = 'CLASS-1')
    OPTIONAL MATCH (c)-[m:MATCHED_TENDER]->(t)
      WHERE m.status IN ['WON', 'LOST'] OR (m.status = 'ALERTED' AND ($now - m.last_alert_sent) < 172800)
    WITH t, d, r, c, m
    WHERE m IS NULL

    // Mandatory Trade Category Gate
    MATCH (t)-[:IN_CATEGORY]->(twc:WorkCategory)<-[:WORKS_IN]-(c)

    // Mandatory Specialization Gate
    WITH t, d, r, c, twc, [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization) | spec] AS req_specs
    WITH t, d, r, c, twc, req_specs, [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization)<-[:HAS_SPECIALIZATION]-(c) | spec] AS held_specs
    WHERE size(held_specs) = size(req_specs)

    // Mandatory Enlistment Class Gate (with valid expiration)
    WITH t, d, r, c, twc, [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec] AS req_enlist
    WITH t, d, r, c, twc, req_enlist, [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass)<-[en:ENLISTED_AS]-(c) WHERE en.valid_until IS NULL OR en.valid_until > $now | ec] AS held_enlist
    WHERE size(held_enlist) = size(req_enlist)

    // Mandatory Technical Certifications Gate (with valid expiration)
    WITH t, d, r, c, twc, [(t)-[:REQUIRES_CERT]->(rc:Certification) | rc] AS req_certs
    WITH t, d, r, c, twc, req_certs, [(t)-[:REQUIRES_CERT]->(rc:Certification)<-[hc:HOLDS_CERT]-(c) WHERE hc.valid_until IS NULL OR hc.valid_until > $now | rc] AS held_certs
    WHERE size(held_certs) = size(req_certs)

    // Mandatory Brand & OEM Strict Authorization Gate (with territorial match & valid expiration)
    WITH t, d, r, c, twc, [(t)-[pb:PREFERS_BRAND]->(b:Brand) WHERE pb.strict_auth_required = true | b] AS req_brands
    WITH t, d, r, c, twc, req_brands, [(t)-[pb:PREFERS_BRAND]->(b:Brand)<-[auth:AUTHORIZED_FOR]-(c) WHERE (auth.valid_until IS NULL OR auth.valid_until > $now) AND (auth.territory IN ['ALL_INDIA', 'All India', r.name]) | b] AS held_brands
    WHERE size(held_brands) = size(req_brands)

    // Product requirements are a hard gate only when the notice explicitly requires
    // OEM/authorized supply (per edge or tender-wide). Other BOQ overlap is scored below.
    WITH t, d, r, c, twc,
         [(t)-[rp:REQUIRES_PRODUCT]->(p:Product)
          WHERE coalesce(t.oem_required, false) = true OR coalesce(rp.requires_oem_or_auth, false) = true | p] AS req_oem_products
    WITH t, d, r, c, twc, req_oem_products,
         [(t)-[rp:REQUIRES_PRODUCT]->(p:Product)<-[sp:SUPPLIES]-(c)
          WHERE ((coalesce(rp.requires_oem_or_auth, false) = false AND coalesce(t.oem_required, false) = false) OR sp.is_oem = true) | p] AS held_oem_products
    WHERE size(held_oem_products) = size(req_oem_products)

    OPTIONAL MATCH (c)-[:HAS_SPECIALIZATION]->(tspec:Specialization)<-[:REQUIRES_SPECIALIZATION]-(t)
    OPTIONAL MATCH (c)-[hc:HOLDS_CERT]->(tcert:Certification)<-[:REQUIRES_CERT]-(t)
      WHERE hc.valid_until IS NULL OR hc.valid_until > $now
    OPTIONAL MATCH (c)-[auth:AUTHORIZED_FOR]->(tb:Brand)<-[:PREFERS_BRAND]-(t)
      WHERE (auth.territory = r.name OR toUpper(replace(auth.territory, ' ', '_')) = 'ALL_INDIA') AND (auth.valid_until IS NULL OR auth.valid_until > $now)
    OPTIONAL MATCH (c)-[sp:SUPPLIES]->(tp:Product)<-[rp:REQUIRES_PRODUCT]-(t)
      WHERE ((coalesce(rp.requires_oem_or_auth, false) = false AND coalesce(t.oem_required, false) = false) OR sp.is_oem = true)
    OPTIONAL MATCH (c)-[en:ENLISTED_AS]->(tec:EnlistmentClass)<-[:REQUIRES_ENLISTMENT]-(t)
      WHERE en.valid_until IS NULL OR en.valid_until > $now
    OPTIONAL MATCH (c)-[da:DEPARTMENT_AFFINITY]->(d)
    OPTIONAL MATCH (c)-[ca:CATEGORY_AFFINITY]->(twc)
    RETURN c.id AS client_id,
           c.name AS client_name,
           c.avg_turnover_3yr AS avg_turnover,
           c.is_msme AS is_msme,
           collect(DISTINCT twc.name) AS matched_wc,
           collect(DISTINCT tspec.name) AS matched_spec,
           collect(DISTINCT tcert.name) AS matched_cert,
           collect(DISTINCT tb.name) AS matched_brands,
           collect(DISTINCT tp.name) AS matched_prods,
           collect(DISTINCT tec.code) AS matched_enlist,
           coalesce(da.affinity_weight, 0.0) AS dept_affinity,
           coalesce(ca.affinity_weight, 0.0) AS cat_affinity
    """
    cand_res = graph.query(candidates_query, {"tender_id": tender_id, "now": now})

    candidates = []
    for row in cand_res.result_set:
        cid = row[0]
        cname = row[1]
        avg_turnover = row[2]
        is_msme = row[3]
        matched_wc = row[4]
        matched_spec = row[5]
        matched_cert = row[6]
        matched_brands = row[7]
        matched_prods = row[8]
        matched_enlist = row[9]
        dept_affinity = float(row[10])
        cat_affinity = float(row[11])

        direct_matched_count = (
            len(matched_wc) +
            len(matched_spec) +
            len(matched_cert) +
            len(matched_brands) +
            len(matched_prods) +
            len(matched_enlist)
        )
        # 3. 5-Hop Lookalike Traversal (Shielded Anchor Analysis)
        # Groups by (client, anchor), requires >= 2 shared capabilities per anchor,
        # and requires >= 2 distinct supporting anchors who previously won in this department & category.
        lookalike_query = """
        MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
        MATCH (t)<-[:ISSUED]-(d:Department)-[:ISSUED]->(past_t:Tender)-[:IN_CATEGORY]->(wc)
        MATCH (anchor:Client)-[:BID_HISTORY {outcome: 'WON'}]->(past_t)
        WHERE anchor.id <> $client_id AND anchor.is_blacklisted = false
        MATCH (anchor)-[:WORKS_IN|HAS_SPECIALIZATION|HOLDS_CERT|AUTHORIZED_FOR|SUPPLIES]->(shared)<-[:WORKS_IN|HAS_SPECIALIZATION|HOLDS_CERT|AUTHORIZED_FOR|SUPPLIES]-(c:Client {id: $client_id})
        WITH anchor, count(DISTINCT shared) AS shared_per_anchor, d
        WHERE shared_per_anchor >= 2
        RETURN count(DISTINCT anchor) AS supporting_anchors, sum(shared_per_anchor) AS total_shared_caps, d.name AS dept_name
        """
        la_res = graph.query(lookalike_query, {"tender_id": tender_id, "client_id": cid})
        supporting_anchors = 0
        total_shared_caps = 0
        dept_name = tender_meta.get("dept_name") or "Procuring Department"
        if la_res.result_set:
            row0 = la_res.result_set[0]
            supporting_anchors = int(row0[0] or 0)
            total_shared_caps = int(row0[1] or 0)
            if len(row0) > 2 and row0[2]:
                dept_name = str(row0[2])

        lookalike_peers = []
        lookalike_boost = 0.0
        if supporting_anchors >= 2:
            lookalike_boost = 0.20 if supporting_anchors >= 3 else 0.15
            lookalike_peers.append({
                "benchmark_reference": "[Generic Peer Benchmark - Identity Shielded]",
                "supporting_anchors": supporting_anchors,
                "shared_capabilities_count": total_shared_caps,
                "department": dept_name,
                "plus_points": [
                    f"Historical capability signal: {total_shared_caps} shared capability links across {supporting_anchors} qualifying winner anchors in {dept_name}.",
                    "The candidate also passed the matching query's regional, financial, and credential gates.",
                    "Historical anchor identities and past tender IDs are withheld."
                ]
            })

        # Deterministic Domain Coverage Filter:
        # A candidate must have at least one overlapping work category (if categories are specified)
        # and non-zero matched capability nodes or a verified lookalike peer,
        # preventing cross-domain mismatch (e.g. cable maker alerted for civil tender).
        req_wc_set = tender_meta.get("req_wc") or set()
        if req_wc_set and not matched_wc and not lookalike_peers:
            continue
        if direct_matched_count == 0 and not lookalike_peers:
            continue

        # 4. Agent Memory Affinity Boost
        learned_affinity_boost = round(max(0.0, dept_affinity + cat_affinity), 4)

        # Composite Match Score: Statutory & domain baseline + technical specs + Lookalike peer + Learned affinity
        if matched_wc:
            spec_ratio = (direct_matched_count - 1) / max(1, total_req_count - 1)
            base_score = 0.55 + (spec_ratio * 0.25)
            raw_score = base_score + lookalike_boost + learned_affinity_boost
            match_score = round(min(1.0, max(0.55, raw_score)), 4)
        elif lookalike_peers:
            base_score = 0.50 + lookalike_boost + learned_affinity_boost
            match_score = round(min(0.90, max(0.50, base_score)), 4)
        else:
            match_score = 0.0

        # Return relationship evidence that corresponds to the actual query patterns.
        evidence_groups = [
            ("WorkCategory", matched_wc, "WORKS_IN", "IN_CATEGORY"),
            ("Specialization", matched_spec, "HAS_SPECIALIZATION", "REQUIRES_SPECIALIZATION"),
            ("Certification", matched_cert, "HOLDS_CERT", "REQUIRES_CERT"),
            ("Brand", matched_brands, "AUTHORIZED_FOR", "PREFERS_BRAND"),
            ("Product", matched_prods, "SUPPLIES", "REQUIRES_PRODUCT"),
            ("EnlistmentClass", matched_enlist, "ENLISTED_AS", "REQUIRES_ENLISTMENT"),
        ]
        graph_evidence = [
            {"node_label": label, "node_name": name, "client_relationship": client_rel,
             "tender_relationship": tender_rel}
            for label, names, client_rel, tender_rel in evidence_groups
            for name in (names or [])
        ]
        matched_capability_count = min(direct_matched_count, total_req_count)
        capability_coverage = round(matched_capability_count / total_req_count, 4)
        if matched_wc:
            base_score = round(base_score, 4)
        score_components = {
            "method": "deterministic_heuristic_fit_score",
            "capability_coverage": capability_coverage,
            "base_fit": round(base_score, 4) if matched_wc or lookalike_peers else 0.0,
            "lookalike_boost": round(lookalike_boost, 4),
            "learned_affinity_boost": learned_affinity_boost,
            "final_fit_score": match_score,
            "is_win_probability": False,
        }
        trace_parts = [
            f"(:Client {{id: '{cid}'}})-[:{item['client_relationship']}]->"
            f"(:{item['node_label']} {{name: '{item['node_name']}'}})<-"
            f"[:{item['tender_relationship']}]-(:Tender {{id: '{tender_id}'}})"
            for item in graph_evidence
        ]
        graph_path_trace = " ; ".join(trace_parts) or "No direct capability path returned."
        if lookalike_peers:
            graph_path_trace += (
                f" | Lookalike signal: {supporting_anchors} qualifying historical-winner anchors; "
                "anchor identities and tender IDs are withheld."
            )

        candidates.append({
            "client_id": cid,
            "client_name": cname,
            "avg_turnover_3yr": avg_turnover,
            "is_msme": is_msme,
            "match_score": match_score,
            "score_components": score_components,
            "eligibility_status": "ELIGIBLE_FOR_MATCHING",
            "direct_matched_nodes": {
                "work_categories": matched_wc,
                "specializations": matched_spec,
                "certifications": matched_cert,
                "brands": matched_brands,
                "products": matched_prods,
                "enlistment": matched_enlist,
            },
            "lookalike_peers": lookalike_peers,
            "graph_evidence": graph_evidence,
            "learned_affinity_boost": learned_affinity_boost,
            "graph_path_trace": graph_path_trace,
        })

    # Sort descending by match score
    candidates.sort(key=lambda x: x["match_score"], reverse=True)

    result = {
        "tender_id": tender_id,
        "tender_title": tender_meta["title"],
        "department": tender_meta["dept_name"],
        "region": tender_meta["region_name"],
        "total_candidates": len(candidates),
        "candidates": candidates,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def discover_jv_consortium_matches(
    tender_id: str,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Finds pairs of non-blacklisted clients (c1 + c2) in the tender's region where neither satisfies
    100% of the requirements alone, but their combined 3-yr turnover satisfies expected_turnover_3yr
    and the union of their capabilities (WorkCategory, Specialization, Certification, Brand, Product,
    and EnlistmentClass) covers 100% of the tender's specifications.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())

    # 1. Fetch Tender Requirements
    t_query = """
    MATCH (t:Tender {id: $tender_id})-[:LOCATED_IN]->(r:Region)
    WHERE (t.status = 'ACTIVE' OR t.status IS NULL)
      AND (t.deadline_at IS NULL OR t.deadline_at > $now)
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    RETURN t.id,
           t.title,
           t.expected_turnover_3yr,
           r.name,
           t.oem_required,
           [(t)-[:IN_CATEGORY]->(twc:WorkCategory) | twc.name] AS wc,
           [(t)-[:REQUIRES_SPECIALIZATION]->(tspec:Specialization) | tspec.name] AS spec,
           [(t)-[:REQUIRES_CERT]->(tcert:Certification) | tcert.name] AS cert,
           [(t)-[pb:PREFERS_BRAND]->(tb:Brand) WHERE pb.strict_auth_required = true | tb.name] AS brands,
           [(t)-[rp:REQUIRES_PRODUCT]->(tp:Product)
             WHERE coalesce(t.oem_required, false) = true OR coalesce(rp.requires_oem_or_auth, false) = true | tp.name] AS prods,
           [(t)-[:REQUIRES_ENLISTMENT]->(tec:EnlistmentClass) | tec.code] AS enlist,
           t.min_net_worth,
           t.min_solvency,
           t.min_tech_staff,
           t.min_local_content_class,
           t.max_ongoing_work_allowed
    """
    t_res = graph.query(t_query, {"tender_id": tender_id, "now": now})
    if not t_res.result_set:
        return json.dumps({"error": f"Tender {tender_id} not found", "total_consortiums_found": 0, "consortiums": []})

    t_row = t_res.result_set[0]
    expected_turnover = float(t_row[2] or 0.0)
    region_name = t_row[3]
    oem_required = bool(t_row[4])

    req_wc = set(t_row[5])
    req_spec = set(t_row[6])
    req_cert = set(t_row[7])
    req_brands = set(t_row[8])
    req_prods = set(t_row[9])
    req_enlist = set(t_row[10])
    min_net_worth = float(t_row[11] or 0.0)
    min_solvency = float(t_row[12] or 0.0)
    min_tech_staff = int(t_row[13] or 0)
    min_local_content_class = t_row[14]
    max_ongoing_work = float(t_row[15]) if t_row[15] is not None else None

    total_requirements_count = (
        len(req_wc) + len(req_spec) + len(req_cert) +
        len(req_brands) + len(req_prods) + len(req_enlist)
    )

    # 2. Fetch all candidate clients in region with their individual capability coverage
    clients_query = """
    MATCH (t:Tender {id: $tender_id})-[:LOCATED_IN]->(r:Region)
    MATCH (c:Client)-[op:OPERATES_IN]->(r)
    WHERE c.is_blacklisted = false AND op.gst_valid = true
    OPTIONAL MATCH (c)-[:WORKS_IN]->(twc:WorkCategory)<-[:IN_CATEGORY]-(t)
    OPTIONAL MATCH (c)-[:HAS_SPECIALIZATION]->(tspec:Specialization)<-[:REQUIRES_SPECIALIZATION]-(t)
    OPTIONAL MATCH (c)-[hc:HOLDS_CERT]->(tcert:Certification)<-[:REQUIRES_CERT]-(t)
      WHERE hc.valid_until IS NULL OR hc.valid_until > $now
    OPTIONAL MATCH (c)-[auth:AUTHORIZED_FOR]->(tb:Brand)<-[:PREFERS_BRAND]-(t)
      WHERE (auth.territory = r.name OR toUpper(replace(auth.territory, ' ', '_')) = 'ALL_INDIA') AND (auth.valid_until IS NULL OR auth.valid_until > $now)
    OPTIONAL MATCH (t)-[rp:REQUIRES_PRODUCT]->(tp:Product)<-[sp:SUPPLIES]-(c)
      WHERE ((coalesce(rp.requires_oem_or_auth, false) = false AND coalesce(t.oem_required, false) = false) OR sp.is_oem = true)
    OPTIONAL MATCH (c)-[en:ENLISTED_AS]->(tec:EnlistmentClass)<-[:REQUIRES_ENLISTMENT]-(t)
      WHERE en.valid_until IS NULL OR en.valid_until > $now
    RETURN c.id AS cid,
           c.name AS cname,
           c.avg_turnover_3yr AS turnover,
           c.net_worth AS net_worth,
           c.solvency AS solvency,
           c.tech_staff_count AS tech_staff,
           collect(DISTINCT twc.name) AS matched_wc,
           collect(DISTINCT tspec.name) AS matched_spec,
           collect(DISTINCT tcert.name) AS matched_cert,
           collect(DISTINCT tb.name) AS matched_brands,
           collect(DISTINCT tp.name) AS matched_prods,
           collect(DISTINCT tec.code) AS matched_enlist,
           c.local_content_class AS local_content_class,
           c.ongoing_work_value AS ongoing_work_value
    """
    c_res = graph.query(clients_query, {"tender_id": tender_id, "now": now})

    def norm_s(vals):
        return {str(v).strip().lower() for v in vals if v}

    client_profiles = []
    for cr in c_res.result_set:
        c_wc = set(cr[6])
        c_spec = set(cr[7])
        c_cert = set(cr[8])
        c_brands = set(cr[9])
        c_prods = set(cr[10])
        c_enlist = set(cr[11])
        c_turnover = float(cr[2] or 0.0)
        c_net_worth = float(cr[3] or 0.0)
        c_solvency = float(cr[4] or 0.0)
        c_tech_staff = int(cr[5] or 0)
        c_local_content = cr[12]
        c_ongoing_work = float(cr[13] or 0.0)

        # Check if client satisfies 100% alone
        satisfies_alone = (
            c_turnover >= expected_turnover and
            c_net_worth >= min_net_worth and
            c_solvency >= min_solvency and
            c_tech_staff >= min_tech_staff and
            (max_ongoing_work is None or c_ongoing_work <= max_ongoing_work) and
            (min_local_content_class in (None, "", "CLASS-2") or c_local_content == "CLASS-1") and
            norm_s(req_wc).issubset(norm_s(c_wc)) and
            norm_s(req_spec).issubset(norm_s(c_spec)) and
            norm_s(req_cert).issubset(norm_s(c_cert)) and
            norm_s(req_brands).issubset(norm_s(c_brands)) and
            norm_s(req_prods).issubset(norm_s(c_prods)) and
            norm_s(req_enlist).issubset(norm_s(c_enlist))
        )

        client_profiles.append({
            "id": cr[0],
            "name": cr[1],
            "turnover": c_turnover,
            "net_worth": c_net_worth,
            "solvency": c_solvency,
            "tech_staff": c_tech_staff,
            "local_content_class": c_local_content,
            "ongoing_work": c_ongoing_work,
            "wc": c_wc,
            "spec": c_spec,
            "cert": c_cert,
            "brands": c_brands,
            "prods": c_prods,
            "enlist": c_enlist,
            "satisfies_alone": satisfies_alone,
        })

    # 3. Find complementary pairs (c1, c2)
    consortiums = []
    num_clients = len(client_profiles)
    for i in range(num_clients):
        for j in range(i + 1, num_clients):
            c1 = client_profiles[i]
            c2 = client_profiles[j]

            # Rule: Neither satisfies 100% alone
            if c1["satisfies_alone"] or c2["satisfies_alone"]:
                continue

            # Combined turnover check
            combined_turnover = c1["turnover"] + c2["turnover"]
            if combined_turnover < expected_turnover:
                continue
            if c1["net_worth"] + c2["net_worth"] < min_net_worth:
                continue
            if c1["solvency"] + c2["solvency"] < min_solvency:
                continue
            if c1["tech_staff"] + c2["tech_staff"] < min_tech_staff:
                continue
            if max_ongoing_work is not None and c1["ongoing_work"] + c2["ongoing_work"] > max_ongoing_work:
                continue
            if min_local_content_class not in (None, "", "CLASS-2") and (
                c1["local_content_class"] != "CLASS-1" or c2["local_content_class"] != "CLASS-1"
            ):
                continue

            # Combined capability coverage check
            union_wc = c1["wc"] | c2["wc"]
            union_spec = c1["spec"] | c2["spec"]
            union_cert = c1["cert"] | c2["cert"]
            union_brands = c1["brands"] | c2["brands"]
            union_prods = c1["prods"] | c2["prods"]
            union_enlist = c1["enlist"] | c2["enlist"]

            covers_all = (
                norm_s(req_wc).issubset(norm_s(union_wc)) and
                norm_s(req_spec).issubset(norm_s(union_spec)) and
                norm_s(req_cert).issubset(norm_s(union_cert)) and
                norm_s(req_brands).issubset(norm_s(union_brands)) and
                norm_s(req_prods).issubset(norm_s(union_prods)) and
                norm_s(req_enlist).issubset(norm_s(union_enlist))
            )

            if covers_all:
                # Designate lead partner (higher turnover or larger qualification base)
                if c1["turnover"] >= c2["turnover"]:
                    lead, partner = c1, c2
                else:
                    lead, partner = c2, c1

                path_trace = (
                    f"JV Consortium: [Lead: {lead['id']} ({', '.join(lead['wc']) or 'Lead'}, turnover: {lead['turnover']/1e7:.1f} Cr)] + "
                    f"[Partner: {partner['id']} ({', '.join(partner['wc']) or 'Partner'}, turnover: {partner['turnover']/1e7:.1f} Cr)] "
                    f"-> 100% requirements satisfied for Tender {tender_id} in {region_name}"
                )

                clean_tid = tender_id.replace('/', '_').replace(' ', '_').replace('-', '_')
                jv_id = f"jv_{lead['id']}_{partner['id']}_{clean_tid}"

                # Calculate dynamic equity share and graph-derived synergy score
                lead_pct = int(round((lead["turnover"] / max(combined_turnover, 1.0)) * 100))
                partner_pct = max(1, 100 - lead_pct)
                lead_equity_share = f"{lead_pct}%"
                partner_equity_share = f"{partner_pct}%"

                # Dynamic graph-derived synergy score: base coverage (100% union) + financial headroom + solvency buffer
                turnover_ratio = combined_turnover / max(expected_turnover, 1.0)
                headroom_bonus = min(0.12, max(0.02, (turnover_ratio - 1.0) * 0.08))
                solvency_sum = lead["solvency"] + partner["solvency"]
                solvency_bonus = min(0.06, max(0.01, (solvency_sum / max(expected_turnover * 2.0, 1.0)) * 0.06))
                synergy_score = round(min(0.99, max(0.75, 0.80 + headroom_bonus + solvency_bonus)), 2)

                # 5-Stage JV Decision Tree for Agent Reasoning & UI Audit
                decision_tree = {
                    "stage1_solo_disqualification": {
                        "title": "Stage 1: Solo Bidder Disqualification Gate",
                        "lead_status": f"{lead['name']} cannot bid alone (Turnover ₹{lead['turnover']/1e7:.2f} Cr vs ₹{expected_turnover/1e7:.2f} Cr required, or lacks specialized turnkey credentials).",
                        "partner_status": f"{partner['name']} cannot bid alone (Turnover ₹{partner['turnover']/1e7:.2f} Cr or missing required statutory authorizations).",
                        "gate_passed": True,
                        "detail": "Neither entity can independently satisfy 100% of CPWD/GeM statutory criteria. Proceeding to Consortium Synthesis."
                    },
                    "stage2_financial_aggregation": {
                        "title": "Stage 2: Financial Aggregation & Solvency Gate",
                        "lead_turnover_cr": round(lead["turnover"] / 1e7, 2),
                        "partner_turnover_cr": round(partner["turnover"] / 1e7, 2),
                        "combined_turnover_cr": round(combined_turnover / 1e7, 2),
                        "required_turnover_cr": round(expected_turnover / 1e7, 2),
                        "combined_net_worth_cr": round((lead["net_worth"] + partner["net_worth"]) / 1e7, 2),
                        "required_net_worth_cr": round(min_net_worth / 1e7, 2),
                        "combined_solvency_cr": round((lead["solvency"] + partner["solvency"]) / 1e7, 2),
                        "required_solvency_cr": round(min_solvency / 1e7, 2),
                        "combined_tech_staff": lead["tech_staff"] + partner["tech_staff"],
                        "required_tech_staff": min_tech_staff,
                        "buffer_cr": round((combined_turnover - expected_turnover) / 1e7, 2),
                        "gate_passed": True,
                        "detail": f"Combined turnover, net worth, solvency, and technical staff meet the configured tender thresholds. Turnover headroom: +₹{(combined_turnover - expected_turnover)/1e7:.2f} Cr."
                    },
                    "stage3_capability_union": {
                        "title": "Stage 3: Multi-Hop Capability Union Gate",
                        "lead_contributions": sorted(list(lead["wc"] | lead["spec"] | lead["cert"] | lead["brands"] | lead["prods"] | lead["enlist"])),
                        "partner_contributions": sorted(list(partner["wc"] | partner["spec"] | partner["cert"] | partner["brands"] | partner["prods"] | partner["enlist"])),
                        "coverage_percentage": 100.0,
                        "gate_passed": True,
                        "detail": "Union of Work Categories, Specializations, Brands, and Products covers 100% of procurement specifications."
                    },
                    "stage4_regional_compliance": {
                        "title": "Stage 4: Regional Registration & Compliance Gate",
                        "region": region_name,
                        "lead_gst": f"Graph records a valid GST relationship in {region_name}",
                        "partner_gst": f"Graph records a valid GST relationship in {region_name}",
                        "blacklisting_status": "Both client nodes have is_blacklisted=false in the graph",
                        "gate_passed": True,
                        "detail": "Both consortium members have valid regional GST relationships and no blacklist flag in the graph. These demo graph values are not external verification."
                    },
                    "stage5_governance_recommendation": {
                        "title": "Stage 5: Consortium Governance & Lead Designation",
                        "designated_lead": lead["name"],
                        "designated_partner": partner["name"],
                        "lead_equity_share": lead_equity_share,
                        "partner_equity_share": partner_equity_share,
                        "synergy_score": synergy_score,
                        "action": "RECOMMEND_JV_FORMATION",
                        "detail": f"Recommended unincorporated Joint Venture with {lead['name']} as Lead Managing Partner ({lead_equity_share} share)."
                    }
                }

                # Persist JVConsortium Node & Edges into FalkorDB
                try:
                    graph.query("""
                    MERGE (jv:JVConsortium {id: $jv_id})
                    SET jv.tender_id = $tender_id,
                        jv.tender_title = $tender_title,
                        jv.lead_id = $lead_id,
                        jv.lead_name = $lead_name,
                        jv.partner_id = $partner_id,
                        jv.partner_name = $partner_name,
                        jv.combined_turnover = $combined_turnover,
                        jv.required_turnover = $required_turnover,
                        jv.synergy_score = $synergy_score,
                        jv.decision_tree_json = $decision_tree_json,
                        jv.status = coalesce(jv.status, 'RECOMMENDED'),
                        jv.created_at = coalesce(jv.created_at, $now),
                        jv.updated_at = $now
                    WITH jv
                    MATCH (lead:Client {id: $lead_id}), (partner:Client {id: $partner_id}), (t:Tender {id: $tender_id})
                    MERGE (lead)-[:LEAD_IN_CONSORTIUM]->(jv)
                    MERGE (partner)-[:PARTNER_IN_CONSORTIUM]->(jv)
                    MERGE (jv)-[:FORMED_FOR_TENDER]->(t)
                    MERGE (lead)-[pa:PARTNERSHIP_AFFINITY]->(partner)
                      ON CREATE SET pa.proposals = 1, pa.wins = 0, pa.losses = 0, pa.affinity_score = $synergy_score
                    """, {
                        "jv_id": jv_id,
                        "tender_id": tender_id,
                        "tender_title": t_row[1],
                        "lead_id": lead["id"],
                        "lead_name": lead["name"],
                        "partner_id": partner["id"],
                        "partner_name": partner["name"],
                        "combined_turnover": combined_turnover,
                        "required_turnover": expected_turnover,
                        "synergy_score": synergy_score,
                        "decision_tree_json": json.dumps(decision_tree),
                        "now": now,
                    })
                except Exception as exc:
                    logger.warning("Could not persist JVConsortium in graph: %s", exc)

                consortiums.append({
                    "id": jv_id,
                    "jv_id": jv_id,
                    "tender_id": tender_id,
                    "tender_title": t_row[1],
                    "lead_partner": {
                        "client_id": lead["id"],
                        "client_name": lead["name"],
                        "avg_turnover_3yr": lead["turnover"],
                        "contributed_nodes": {
                            "work_categories": sorted(list(lead["wc"])),
                            "specializations": sorted(list(lead["spec"])),
                            "certifications": sorted(list(lead["cert"])),
                            "brands": sorted(list(lead["brands"])),
                            "products": sorted(list(lead["prods"])),
                            "enlistment": sorted(list(lead["enlist"])),
                        }
                    },
                    "consortium_partner": {
                        "client_id": partner["id"],
                        "client_name": partner["name"],
                        "avg_turnover_3yr": partner["turnover"],
                        "contributed_nodes": {
                            "work_categories": sorted(list(partner["wc"])),
                            "specializations": sorted(list(partner["spec"])),
                            "certifications": sorted(list(partner["cert"])),
                            "brands": sorted(list(partner["brands"])),
                            "products": sorted(list(partner["prods"])),
                            "enlistment": sorted(list(partner["enlist"])),
                        }
                    },
                    "combined_financials": {
                        "combined_turnover": combined_turnover,
                        "required_turnover": expected_turnover,
                        "turnover_satisfied": True,
                        "combined_net_worth": lead["net_worth"] + partner["net_worth"],
                        "combined_solvency": lead["solvency"] + partner["solvency"],
                        "combined_tech_staff": lead["tech_staff"] + partner["tech_staff"],
                    },
                    "coverage_percentage": 100.0,
                    "synergy_score": synergy_score,
                    "status": "RECOMMENDED",
                    "decision_tree": decision_tree,
                    "graph_path_trace": path_trace,
                })

    return json.dumps({
        "tender_id": tender_id,
        "tender_title": t_row[1],
        "expected_turnover_3yr": expected_turnover,
        "region": region_name,
        "total_consortiums_found": len(consortiums),
        "consortiums": consortiums,
    }, indent=2)


@mcp.tool()
def dispatch_tender_alert_with_trace(
    client_id: str,
    tender_id: str,
    match_score: float,
    match_type: str,
    reasoning_trace: str,
    path_summary: str,
    evaluating_agent: Optional[str] = None,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Enforces the strict 2-day (172,800 seconds) alert cooldown inside FalkorDB.
    If the client is on active cooldown or in terminal status (WON/LOST), dispatch is denied.
    Otherwise, creates/updates :MATCHED_TENDER and logs an :AgentDecision node with full reasoning trace.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())

    # Infer agent label if omitted
    if not evaluating_agent:
        trace_upper = (reasoning_trace or "").upper()
        if "AGENT BETA" in trace_upper or "KEY 2" in trace_upper:
            evaluating_agent = "Agent Beta (NVIDIA Nemotron Key 2)"
        elif "AGENT ALPHA" in trace_upper or "KEY 1" in trace_upper:
            evaluating_agent = "Agent Alpha (NVIDIA Nemotron Key 1)"
        else:
            evaluating_agent = "Agent Alpha (NVIDIA Nemotron Key 1)"

    # 1. Cooldown & Terminal State Check in Cypher
    check_query = """
    MATCH (c:Client {id: $client_id}), (t:Tender {id: $tender_id})
    OPTIONAL MATCH (c)-[m:MATCHED_TENDER]->(t)
    RETURN m.status AS status,
           m.last_alert_sent AS last_alert_sent,
           m.alert_count AS alert_count
    """
    check_res = graph.query(check_query, {"client_id": client_id, "tender_id": tender_id})
    if not check_res.result_set:
        return json.dumps({
            "sent": False,
            "reason": "CLIENT_OR_TENDER_NOT_FOUND",
            "client_id": client_id,
            "tender_id": tender_id,
        })

    row = check_res.result_set[0]
    status = row[0]
    last_alert_sent = row[1]
    alert_count = row[2]

    # Rule A: Terminal Status (WON or LOST) -> Block alert
    if status in ["WON", "LOST"]:
        return json.dumps({
            "sent": False,
            "reason": "TERMINAL_STATUS",
            "status": status,
            "client_id": client_id,
            "tender_id": tender_id,
        })

    # Rule B: 2-Day (48-Hour / 172,800s) Cooldown Active
    if status == "ALERTED" and last_alert_sent is not None:
        elapsed = now - last_alert_sent
        if elapsed < 172800:
            return json.dumps({
                "sent": False,
                "reason": "COOLDOWN_ACTIVE_UNDER_48H",
                "seconds_remaining": int(172800 - elapsed),
                "client_id": client_id,
                "tender_id": tender_id,
            })

    # Rule C: Cooldown passed or first alert -> Dispatch and update graph
    decision_id = f"dec-{uuid.uuid4().hex[:12]}"
    dispatch_query = """
    MATCH (c:Client {id: $client_id}), (t:Tender {id: $tender_id})
    MERGE (c)-[r:MATCHED_TENDER]->(t)
    SET r.last_alert_sent = $now,
        r.alert_count = coalesce(r.alert_count, 0) + 1,
        r.status = 'ALERTED',
        r.match_score = $match_score,
        r.match_type = $match_type,
        r.evaluating_agent = $evaluating_agent,
        r.first_matched_at = coalesce(r.first_matched_at, $now)
    CREATE (ad:AgentDecision {
        id: $decision_id,
        decision_type: 'ALERT_DISPATCHED',
        reasoning_trace: $reasoning_trace,
        path_summary: $path_summary,
        match_score: $match_score,
        evaluating_agent: $evaluating_agent,
        created_at: $now,
        outcome_feedback: 'PENDING'
    })
    CREATE (ad)-[:FOR_CLIENT]->(c)
    CREATE (ad)-[:EVALUATED_TENDER]->(t)
    RETURN r.alert_count AS alert_count, r.status AS status, ad.id AS decision_id
    """
    write_res = graph.query(dispatch_query, {
        "client_id": client_id,
        "tender_id": tender_id,
        "now": now,
        "match_score": match_score,
        "match_type": match_type,
        "evaluating_agent": evaluating_agent,
        "decision_id": decision_id,
        "reasoning_trace": reasoning_trace,
        "path_summary": path_summary,
    })

    w_row = write_res.result_set[0]
    return json.dumps({
        "sent": True,
        "client_id": client_id,
        "tender_id": tender_id,
        "evaluating_agent": evaluating_agent,
        "alert_count": w_row[0],
        "status": w_row[1],
        "decision_id": w_row[2],
        "last_alert_sent": now,
        "match_score": match_score,
        "match_type": match_type,
    }, indent=2)


@mcp.tool()
def record_bid_outcome_and_learn(
    client_id: str,
    tender_id: str,
    outcome: str,
    feedback_notes: str = "",
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Records Won/Lost bid outcome on :MATCHED_TENDER and :BID_HISTORY, updates :AgentDecision,
    and runs the graph learning loop updating :DEPARTMENT_AFFINITY and :CATEGORY_AFFINITY
    with dynamic win-rate calculations and affinity weights.
    """
    clean_outcome = outcome.strip().upper()
    if clean_outcome not in ["WON", "LOST"]:
        raise ValueError(f"Invalid outcome '{outcome}'. Expected 'WON' or 'LOST'.")

    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())

    # 0. Check existing match state for idempotency & double-click protection
    existing_check = graph.query("""
    MATCH (c:Client {id: $client_id})-[m:MATCHED_TENDER]->(t:Tender {id: $tender_id})
    RETURN m.status AS status
    """, {"client_id": client_id, "tender_id": tender_id})

    prev_status = None
    if existing_check.result_set and existing_check.result_set[0] and existing_check.result_set[0][0]:
        prev_status = str(existing_check.result_set[0][0]).upper()

    if prev_status == clean_outcome:
        logger.info("Outcome '%s' already recorded for Client '%s' on Tender '%s'. Re-confirming and refreshing updated_at timestamp.", clean_outcome, client_id, tender_id)
        # Refresh updated_at on existing DEPARTMENT_AFFINITY
        graph.query("""
        MATCH (t:Tender {id: $tender_id})<-[:ISSUED]-(d:Department)
        MATCH (c:Client {id: $client_id})-[da:DEPARTMENT_AFFINITY]->(d)
        SET da.updated_at = $now
        """, {"client_id": client_id, "tender_id": tender_id, "now": now})

        # Refresh updated_at on existing CATEGORY_AFFINITY
        graph.query("""
        MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
        MATCH (c:Client {id: $client_id})-[ca:CATEGORY_AFFINITY]->(wc)
        SET ca.updated_at = $now
        """, {"client_id": client_id, "tender_id": tender_id, "now": now})

        cur_dept = graph.query("""
        MATCH (t:Tender {id: $tender_id})<-[:ISSUED]-(d:Department)
        MATCH (c:Client {id: $client_id})-[da:DEPARTMENT_AFFINITY]->(d)
        RETURN d.name, da.wins, da.losses, da.win_rate, da.affinity_weight
        """, {"client_id": client_id, "tender_id": tender_id})
        dept_info = {}
        if cur_dept.result_set:
            r = cur_dept.result_set[0]
            dept_info = {"status": "UPDATED", "department_name": r[0], "wins": r[1], "losses": r[2], "win_rate": r[3], "affinity_weight": r[4]}
        else:
            dept_info = {
                "status": "NO_DEPARTMENT",
                "message": "No procuring department associated with tender; department affinity memory skipped.",
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "affinity_weight": 0.0,
            }

        cur_cats = graph.query("""
        MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
        MATCH (c:Client {id: $client_id})-[ca:CATEGORY_AFFINITY]->(wc)
        RETURN wc.name, ca.wins, ca.losses, ca.win_rate, ca.affinity_weight
        """, {"client_id": client_id, "tender_id": tender_id})
        cat_info = []
        for cr in cur_cats.result_set:
            cat_info.append({"category_name": cr[0], "wins": cr[1], "losses": cr[2], "win_rate": cr[3], "affinity_weight": cr[4]})

        return json.dumps({
            "success": True,
            "client_id": client_id,
            "tender_id": tender_id,
            "outcome": clean_outcome,
            "resolved_at": now,
            "department_affinity": dept_info,
            "category_affinities": cat_info,
            "idempotent_skip": True,
        }, indent=2)

    # Compute deltas for wins and losses to support correction (e.g. from WON to LOST or vice versa)
    if prev_status == "WON" and clean_outcome == "LOST":
        win_delta = -1
        loss_delta = 1
    elif prev_status == "LOST" and clean_outcome == "WON":
        win_delta = 1
        loss_delta = -1
    elif clean_outcome == "WON":
        win_delta = 1
        loss_delta = 0
    else:
        win_delta = 0
        loss_delta = 1

    # 1. Update Client node properties, MATCHED_TENDER edge, and record BID_HISTORY
    graph.query("""
    MATCH (c:Client {id: $client_id}), (t:Tender {id: $tender_id})
    SET c.total_bids_won = CASE WHEN coalesce(c.total_bids_won, 0) + $win_delta < 0 THEN 0 ELSE coalesce(c.total_bids_won, 0) + $win_delta END,
        c.total_bids_lost = CASE WHEN coalesce(c.total_bids_lost, 0) + $loss_delta < 0 THEN 0 ELSE coalesce(c.total_bids_lost, 0) + $loss_delta END,
        c.last_outcome = $outcome,
        c.last_won_tender = CASE WHEN $outcome = 'WON' THEN $tender_id ELSE c.last_won_tender END,
        c.last_outcome_at = $now
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    ON CREATE SET m.match_score = coalesce(m.match_score, 0.50), m.match_type = 'DIRECT', m.alert_count = 1, m.first_matched_at = $now, m.last_alert_sent = $now
    SET m.status = $outcome,
        m.resolved_at = $now
    MERGE (c)-[b:BID_HISTORY]->(t)
    SET b.outcome = $outcome,
        b.recorded_at = $now,
        b.feedback_notes = $feedback_notes
    """, {
        "client_id": client_id,
        "tender_id": tender_id,
        "outcome": clean_outcome,
        "now": now,
        "feedback_notes": feedback_notes,
        "win_delta": win_delta,
        "loss_delta": loss_delta,
    })

    # 2. Update latest AgentDecision outcome_feedback
    graph.query("""
    MATCH (ad:AgentDecision)-[:FOR_CLIENT]->(c:Client {id: $client_id})
    WHERE (ad)-[:EVALUATED_TENDER]->(:Tender {id: $tender_id})
    SET ad.outcome_feedback = $outcome
    """, {
        "client_id": client_id,
        "tender_id": tender_id,
        "outcome": clean_outcome,
    })

    # 3. Graph Memory Update: Update DEPARTMENT_AFFINITY with Laplace smoothing & division-by-zero protection
    dept_res = graph.query("""
    MATCH (t:Tender {id: $tender_id})<-[:ISSUED]-(d:Department)
    MATCH (c:Client {id: $client_id})
    MERGE (c)-[da:DEPARTMENT_AFFINITY]->(d)
    SET da.wins = CASE WHEN coalesce(da.wins, 0) + $win_delta < 0 THEN 0 ELSE coalesce(da.wins, 0) + $win_delta END,
        da.losses = CASE WHEN coalesce(da.losses, 0) + $loss_delta < 0 THEN 0 ELSE coalesce(da.losses, 0) + $loss_delta END,
        da.updated_at = $now
    WITH da, (da.wins + da.losses) AS total_bids, d
    SET da.win_rate = CASE 
            WHEN total_bids = 0 THEN 0.0 
            ELSE round((toFloat(da.wins) / toFloat(total_bids)) * 10000.0) / 10000.0 
        END,
        da.affinity_weight = round(((toFloat(da.wins + 1) / toFloat(total_bids + 2)) - 0.5) * 0.5 * 10000.0) / 10000.0
    RETURN d.name AS dept_name, da.wins AS wins, da.losses AS losses, da.win_rate AS win_rate, da.affinity_weight AS affinity_weight
    """, {
        "client_id": client_id,
        "tender_id": tender_id,
        "outcome": clean_outcome,
        "now": now,
        "win_delta": win_delta,
        "loss_delta": loss_delta,
    })
    dept_info = {}
    if dept_res.result_set:
        d_row = dept_res.result_set[0]
        dept_info = {
            "status": "UPDATED",
            "department_name": d_row[0],
            "wins": d_row[1],
            "losses": d_row[2],
            "win_rate": d_row[3],
            "affinity_weight": d_row[4],
        }
    else:
        dept_info = {
            "status": "NO_DEPARTMENT",
            "message": "No procuring department associated with tender; department affinity memory skipped.",
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "affinity_weight": 0.0,
        }

    # 4. Graph Memory Update: Update CATEGORY_AFFINITY with Laplace smoothing & division-by-zero protection
    cat_res = graph.query("""
    MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
    MATCH (c:Client {id: $client_id})
    MERGE (c)-[ca:CATEGORY_AFFINITY]->(wc)
    SET ca.wins = CASE WHEN coalesce(ca.wins, 0) + $win_delta < 0 THEN 0 ELSE coalesce(ca.wins, 0) + $win_delta END,
        ca.losses = CASE WHEN coalesce(ca.losses, 0) + $loss_delta < 0 THEN 0 ELSE coalesce(ca.losses, 0) + $loss_delta END,
        ca.updated_at = $now
    WITH ca, (ca.wins + ca.losses) AS total_bids, wc
    SET ca.win_rate = CASE 
            WHEN total_bids = 0 THEN 0.0 
            ELSE round((toFloat(ca.wins) / toFloat(total_bids)) * 10000.0) / 10000.0 
        END,
        ca.affinity_weight = round(((toFloat(ca.wins + 1) / toFloat(total_bids + 2)) - 0.5) * 0.5 * 10000.0) / 10000.0
    RETURN wc.name AS category_name, ca.wins AS wins, ca.losses AS losses, ca.win_rate AS win_rate, ca.affinity_weight AS affinity_weight
    """, {
        "client_id": client_id,
        "tender_id": tender_id,
        "outcome": clean_outcome,
        "now": now,
        "win_delta": win_delta,
        "loss_delta": loss_delta,
    })
    category_affinities = []
    for c_row in cat_res.result_set:
        category_affinities.append({
            "category_name": c_row[0],
            "wins": c_row[1],
            "losses": c_row[2],
            "win_rate": c_row[3],
            "affinity_weight": c_row[4],
        })

    # 5. Graph Learning Loop: Update JVConsortium & Partnership Affinity if part of a JV
    try:
        graph.query("""
        MATCH (jv:JVConsortium)-[:FORMED_FOR_TENDER]->(t:Tender {id: $tender_id})
        WHERE jv.lead_id = $client_id OR jv.partner_id = $client_id
        SET jv.status = $outcome, jv.updated_at = $now
        WITH jv
        MATCH (lead:Client {id: jv.lead_id})-[pa:PARTNERSHIP_AFFINITY]->(partner:Client {id: jv.partner_id})
        SET pa.wins = coalesce(pa.wins, 0) + CASE WHEN $outcome = 'WON' THEN 1 ELSE 0 END,
            pa.losses = coalesce(pa.losses, 0) + CASE WHEN $outcome = 'LOST' THEN 1 ELSE 0 END,
            pa.affinity_score = CASE WHEN $outcome = 'WON' THEN 0.98 ELSE 0.65 END,
            pa.updated_at = $now
        """, {
            "tender_id": tender_id,
            "client_id": client_id,
            "outcome": clean_outcome,
            "now": now,
        })
    except Exception as exc:
        logger.warning("Could not cascade outcome to JVConsortium: %s", exc)

    result = {
        "success": True,
        "client_id": client_id,
        "tender_id": tender_id,
        "outcome": clean_outcome,
        "resolved_at": now,
        "department_affinity": dept_info,
        "category_affinities": category_affinities,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def execute_read_cypher(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Diagnostic tool: executes a read-only OpenCypher query against FalkorDB and returns JSON result rows.
    Mutating statements (CREATE, MERGE, SET, DELETE, DROP) are strictly rejected.
    """
    validation_error = _read_only_query_error(query)
    if validation_error:
        return json.dumps({"error": validation_error})

    graph = _get_target_graph(graph_name)
    try:
        res = graph.query(query, params=params or {})
        columns = [col[1] for col in res.header] if hasattr(res, "header") and res.header else []
        rows = [list(row) for row in res.result_set]
        return json.dumps({
            "query": query,
            "columns": columns,
            "row_count": len(rows),
            "rows": rows,
        }, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc), "query": query})


@mcp.tool()
def get_alerts_and_agent_memory(
    client_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Queries alert history, active cooldown states, agent decision traces, and all learned
    DEPARTMENT_AFFINITY and CATEGORY_AFFINITY edges across clients for UI dashboard feeds.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())

    # 1. Fetch Alert History with Joined Department, Ministry, Latest AgentDecision & Department Affinity
    alerts_query = """
    MATCH (c:Client)-[m:MATCHED_TENDER]->(t:Tender)
    WHERE ($client_id IS NULL OR c.id = $client_id)
      AND ($status_filter IS NULL OR m.status = $status_filter)
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    OPTIONAL MATCH (min:Ministry)-[:HAS_DEPARTMENT]->(d)
    OPTIONAL MATCH (c)-[da:DEPARTMENT_AFFINITY]->(d)
    OPTIONAL MATCH (ad:AgentDecision)-[:FOR_CLIENT]->(c)
    WHERE (ad)-[:EVALUATED_TENDER]->(t)
    WITH c, m, t, d, min, da, ad
    ORDER BY ad.created_at DESC
    WITH c, m, t, d, min, da, head(collect(ad)) AS latest_ad
    RETURN c.id AS client_id,
           c.name AS client_name,
           t.id AS tender_id,
           t.title AS tender_title,
           d.name AS department_name,
           min.name AS ministry_name,
           t.tender_amount AS tender_amount,
           m.match_score AS match_score,
           m.match_type AS match_type,
           m.status AS status,
           m.alert_count AS alert_count,
           m.first_matched_at AS first_matched_at,
           m.last_alert_sent AS last_alert_sent,
           latest_ad.reasoning_trace AS reasoning_trace,
           latest_ad.path_summary AS path_summary,
           da.wins AS wins,
           da.losses AS losses,
           da.win_rate AS win_rate,
           da.affinity_weight AS affinity_weight,
           coalesce(c.email, 'hackathon-demo@outlook.com') AS client_email,
           t.deadline_at AS tender_deadline,
           coalesce(latest_ad.evaluating_agent, m.evaluating_agent) AS evaluating_agent
    ORDER BY m.last_alert_sent DESC
    """
    alerts_res = graph.query(alerts_query, {
        "client_id": client_id,
        "status_filter": status_filter,
    })

    alerts = []
    seen_pairs = set()
    for row in alerts_res.result_set:
        client_id_val = row[0]
        tender_id_val = row[2]
        pair_key = (client_id_val, tender_id_val)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        status = row[9]
        last_sent = row[12]
        cooldown_active = False
        cooldown_rem = 0
        if status == "ALERTED" and last_sent is not None:
            elapsed = now - last_sent
            if elapsed < 172800:
                cooldown_active = True
                cooldown_rem = int(max(0, 172800 - elapsed))

        dept_affinity = None
        if row[15] is not None:
            dept_affinity = {
                "wins": row[15],
                "losses": row[16],
                "win_rate": row[17],
                "affinity_weight": row[18],
            }

        trace_text = row[13] or "Automated graph matching qualification."
        raw_agent = row[21] if len(row) > 21 and row[21] else None
        if raw_agent:
            eval_agent = raw_agent
        elif "AGENT BETA" in trace_text.upper() or "KEY 2" in trace_text.upper():
            eval_agent = "Agent Beta (Key 2)"
        elif "AGENT ALPHA" in trace_text.upper() or "KEY 1" in trace_text.upper():
            eval_agent = "Agent Alpha (Key 1)"
        else:
            eval_agent = "Agent Alpha (Key 1)"

        alerts.append({
            "client_id": client_id_val,
            "client_name": row[1],
            "tender_id": tender_id_val,
            "tender_title": row[3],
            "department_name": row[4] or "Procurement Department",
            "ministry_name": row[5] or "Government of India",
            "tender_amount": row[6],
            "match_score": float(row[7]) if row[7] is not None else 0.90,
            "match_type": str(row[8]) if row[8] is not None else "DIRECT",
            "status": status,
            "alert_count": int(row[10]) if row[10] is not None else 1,
            "first_matched_at": row[11],
            "last_alert_sent": last_sent,
            "cooldown_active": cooldown_active,
            "cooldown_seconds_remaining": cooldown_rem,
            "reasoning_trace": trace_text,
            "path_summary": row[14] or "Direct match traversal.",
            "department_affinity": dept_affinity,
            "client_email": row[19] if len(row) > 19 else None,
            "tender_deadline": row[20] if len(row) > 20 else None,
            "evaluating_agent": eval_agent,
        })

    # 2. Fetch Learned Affinities (Filtered by client_id if requested, sorted by most recently updated)
    learned_affinities = []

    dept_aff_res = graph.query("""
    MATCH (c:Client)-[da:DEPARTMENT_AFFINITY]->(d:Department)
    WHERE ($client_id IS NULL OR c.id = $client_id)
    RETURN c.id, c.name, d.name, 'DEPARTMENT',
           da.wins, da.losses, da.win_rate, da.affinity_weight, coalesce(da.updated_at, 0) AS updated_at
    ORDER BY updated_at DESC, da.affinity_weight DESC
    """, {"client_id": client_id})
    for r in dept_aff_res.result_set:
        learned_affinities.append({
            "client_id": r[0],
            "client_name": r[1],
            "target_entity": r[2],
            "affinity_type": "DEPARTMENT",
            "wins": r[4],
            "losses": r[5],
            "win_rate": r[6],
            "affinity_weight": r[7],
            "updated_at": r[8] if r[8] else None,
        })

    cat_aff_res = graph.query("""
    MATCH (c:Client)-[ca:CATEGORY_AFFINITY]->(wc:WorkCategory)
    WHERE ($client_id IS NULL OR c.id = $client_id)
    RETURN c.id, c.name, wc.name, 'CATEGORY',
           ca.wins, ca.losses, ca.win_rate, ca.affinity_weight, coalesce(ca.updated_at, 0) AS updated_at
    ORDER BY updated_at DESC, ca.affinity_weight DESC
    """, {"client_id": client_id})
    for r in cat_aff_res.result_set:
        learned_affinities.append({
            "client_id": r[0],
            "client_name": r[1],
            "target_entity": r[2],
            "affinity_type": "CATEGORY",
            "wins": r[4],
            "losses": r[5],
            "win_rate": r[6],
            "affinity_weight": r[7],
            "updated_at": r[8] if r[8] else None,
        })

    # Sort combined affinities so the most recently updated item appears first, followed by affinity weight
    learned_affinities.sort(key=lambda x: (x.get("updated_at") or 0, x.get("affinity_weight") or 0.0), reverse=True)

    # 3. Fetch JV Consortiums from Graph
    jv_consortiums = []
    try:
        jv_res = graph.query("""
        MATCH (jv:JVConsortium)-[:FORMED_FOR_TENDER]->(t:Tender)
        RETURN jv.id, jv.tender_id, coalesce(jv.tender_title, t.title),
               jv.lead_id, jv.lead_name, jv.partner_id, jv.partner_name,
               jv.combined_turnover, jv.required_turnover, jv.synergy_score,
               jv.status, jv.decision_tree_json, jv.created_at
        ORDER BY jv.created_at DESC
        """)
        for jr in jv_res.result_set:
            dt_dict = {}
            if jr[11]:
                try:
                    dt_dict = json.loads(jr[11]) if isinstance(jr[11], str) else jr[11]
                except Exception:
                    dt_dict = {}
            jv_consortiums.append({
                "id": str(jr[0]),
                "jv_id": str(jr[0]),
                "tender_id": str(jr[1]),
                "tender_title": str(jr[2]),
                "lead_id": str(jr[3]),
                "lead_name": str(jr[4]),
                "partner_id": str(jr[5]),
                "partner_name": str(jr[6]),
                "combined_turnover": float(jr[7] or 0),
                "required_turnover": float(jr[8] or 0),
                "synergy_score": float(jr[9] or 0.96),
                "status": str(jr[10] or "RECOMMENDED"),
                "decision_tree": dt_dict,
                "created_at": jr[12],
            })
    except Exception as exc:
        logger.warning("Error fetching JV consortiums: %s", exc)

    return json.dumps({
        "alerts_count": len(alerts),
        "alerts": alerts,
        "learned_affinities_count": len(learned_affinities),
        "learned_affinities": learned_affinities,
        "jv_consortiums_count": len(jv_consortiums),
        "jv_consortiums": jv_consortiums,
        "query_timestamp": now,
    }, indent=2)


@mcp.tool()
def record_jv_outcome_and_learn(
    jv_id: str,
    outcome: str,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Records Won or Lost outcome for a Joint Venture (JV) Consortium and updates the
    partnership affinity edge (:PARTNERSHIP_AFFINITY) between lead and partner in FalkorDB.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())
    clean_outcome = outcome.strip().upper()
    if clean_outcome not in ["WON", "LOST"]:
        return json.dumps({"error": f"Invalid outcome '{outcome}'. Expected 'WON' or 'LOST'.", "success": False})

    try:
        res = graph.query("""
        MATCH (jv:JVConsortium {id: $jv_id})
        SET jv.status = $outcome, jv.updated_at = $now
        WITH jv
        MATCH (lead:Client {id: jv.lead_id}), (partner:Client {id: jv.partner_id})
        SET lead.total_jv_won = coalesce(lead.total_jv_won, 0) + CASE WHEN $outcome = 'WON' THEN 1 ELSE 0 END,
            partner.total_jv_won = coalesce(partner.total_jv_won, 0) + CASE WHEN $outcome = 'WON' THEN 1 ELSE 0 END
        WITH jv, lead, partner
        MATCH (lead)-[pa:PARTNERSHIP_AFFINITY]->(partner)
        SET pa.wins = coalesce(pa.wins, 0) + CASE WHEN $outcome = 'WON' THEN 1 ELSE 0 END,
            pa.losses = coalesce(pa.losses, 0) + CASE WHEN $outcome = 'LOST' THEN 1 ELSE 0 END,
            pa.affinity_score = CASE WHEN $outcome = 'WON' THEN 0.98 ELSE 0.65 END,
            pa.updated_at = $now
        RETURN jv.id, jv.lead_name, jv.partner_name, jv.status, pa.wins, pa.losses, pa.affinity_score
        """, {
            "jv_id": jv_id,
            "outcome": clean_outcome,
            "now": now,
        })
        if res.result_set:
            row = res.result_set[0]
            return json.dumps({
                "success": True,
                "jv_id": row[0],
                "lead_name": row[1],
                "partner_name": row[2],
                "status": row[3],
                "wins": row[4],
                "losses": row[5],
                "affinity_score": row[6],
                "resolved_at": now,
            }, indent=2)
        else:
            return json.dumps({"error": f"JV Consortium '{jv_id}' not found", "success": False})
    except Exception as exc:
        return json.dumps({"error": str(exc), "success": False})



@mcp.tool()
def get_graph_visualization_snapshot(
    limit_edges: int = 150,
    graph_name: Optional[str] = None
) -> str:
    """
    Returns graph snapshot for UI visualization (nodes, links, and topological summary counts).
    """
    graph = _get_target_graph(graph_name)

    nodes_res = graph.query("""
    MATCH (n)
    RETURN id(n) AS id, labels(n)[0] AS label, properties(n) AS props
    """)
    nodes = []
    for row in nodes_res.result_set:
        nid = str(row[0])
        label = row[1] or "Entity"
        props = dict(row[2]) if row[2] else {}
        name = props.get("name") or props.get("title") or props.get("id") or props.get("code") or nid
        nodes.append({
            "id": nid,
            "name": str(name),
            "label": label,
            "type": label,
            "properties": props,
        })

    edges_query = f"""
    MATCH (s)-[r]->(t)
    RETURN id(s) AS source, id(t) AS target, type(r) AS rel_type, properties(r) AS props
    LIMIT {int(limit_edges)}
    """
    edges_res = graph.query(edges_query)
    links = []
    for row in edges_res.result_set:
        links.append({
            "source": str(row[0]),
            "target": str(row[1]),
            "relationship": row[2],
            "properties": dict(row[3]) if row[3] else {},
        })

    return json.dumps({
        "nodes": nodes,
        "links": links,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(links),
        }
    }, indent=2)


@mcp.tool()
def enrich_and_ingest_tender(
    raw_data_json: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Enriches raw scraped tender JSON using the EnricherIngestor pipeline and upserts
    all nodes/edges into FalkorDB with a scraper heartbeat update.
    """
    from pipeline.enricher_ingestor import EnricherIngestor
    raw_dict = json.loads(raw_data_json) if isinstance(raw_data_json, str) else raw_data_json
    target_graph = _get_target_graph(graph_name)
    ingestor = EnricherIngestor(graph_name=target_graph.name)
    enriched = ingestor.enrich_tender(raw_dict)
    res = ingestor.upsert_tender(enriched, graph=target_graph)
    return json.dumps(res, indent=2)


@mcp.tool()
def scrape_and_ingest_live_tenders(
    portals: Optional[List[str]] = None,
    limit: int = 10,
    delete_existing_active: bool = False,
    graph_name: Optional[str] = None
) -> str:
    """
    Scrapes real-time tenders from actual Indian government procurement portals (GeM & CPPP),
    enriches them with synthetic eligibility/BOQ/financial norms via EnricherIngestor,
    and upserts them into FalkorDB with updated scraper heartbeat telemetry.
    """
    from pipeline.enricher_ingestor import EnricherIngestor
    if isinstance(portals, str):
        try:
            portals = json.loads(portals)
        except Exception:
            portals = [portals]
    chosen_portals = portals or ["gem", "cppp"]
    target_graph = _get_target_graph(graph_name)
    ingestor = EnricherIngestor(graph_name=target_graph.name)
    result = ingestor.scrape_and_ingest_live(
        portals=chosen_portals,
        limit=limit,
        delete_existing_active=delete_existing_active,
        graph=target_graph,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_all_active_tenders_mcp(
    graph_name: Optional[str] = None
) -> str:
    """
    Deletes all active tender records and stale matches/alerts from FalkorDB.
    """
    from pipeline.enricher_ingestor import EnricherIngestor
    target_graph = _get_target_graph(graph_name)
    ingestor = EnricherIngestor(graph_name=target_graph.name)
    result = ingestor.delete_all_active_tenders(graph=target_graph)
    return json.dumps(result, indent=2)


@mcp.tool()
def reset_and_seed_demo_graph(
    graph_name: Optional[str] = None
) -> str:
    """
    Resets and seeds the active FalkorDB graph back to the deterministic initial benchmark state.
    Returns node/edge counts and the initial scraper_status timestamp.
    """
    from db.seed_graph import seed_database
    target_graph = _get_target_graph(graph_name)
    seed_result = seed_database(graph_name=target_graph.name, clear_existing=True)
    seed_result["success"] = (seed_result.get("status") == "success")
    seed_result["benchmark_tenders_seeded"] = seed_result.get("tenders", 0)
    seed_result["benchmark_clients_seeded"] = seed_result.get("clients", 0)
    seed_result["graph_name"] = target_graph.name
    return json.dumps(seed_result, indent=2)


@mcp.tool()
def execute_cypher_traversal(
    cypher_query: str,
    params_json: Optional[str] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Executes a read-only OpenCypher graph traversal query against FalkorDB.
    Enables AI Agents to dynamically formulate and execute multi-hop Cypher queries,
    explore connected nodes, verify client statutory plus points, and traverse lookalike paths.
    """
    clean_q = cypher_query.strip()
    validation_error = _read_only_query_error(clean_q)
    if validation_error:
        return json.dumps({"error": validation_error, "success": False})

    try:
        params = json.loads(params_json) if params_json and isinstance(params_json, str) else (params_json or {})
        target_graph = _get_target_graph(graph_name)
        res = target_graph.query(clean_q, params)
        columns = [col for col in getattr(res, "header", [])] if hasattr(res, "header") else []
        records = []
        for row in res.result_set:
            if columns and len(columns) == len(row):
                records.append(dict(zip(columns, row)))
            else:
                records.append(list(row))
        return json.dumps({
            "success": True,
            "query": clean_q,
            "record_count": len(records),
            "records": records,
        }, indent=2, default=str)
    except Exception as exc:
        return json.dumps({
            "error": str(exc),
            "query": clean_q,
            "success": False
        }, indent=2)


@mcp.tool()
def get_tender_requirements(
    tender_id: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Template Tool 1: Queries all statutory, technical, brand, and regional requirement nodes
    for a specific tender using an explainable, parameterized Cypher template.
    """
    graph = _get_target_graph(graph_name)
    query = """
    MATCH (t:Tender {id: $tender_id})
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    OPTIONAL MATCH (m:Ministry)-[:HAS_DEPARTMENT]->(d)
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(r:Region)
    RETURN t.id AS id,
           t.title AS title,
           t.tender_amount AS tender_amount,
           t.expected_turnover_3yr AS expected_turnover_3yr,
           t.min_net_worth AS min_net_worth,
           t.min_solvency AS min_solvency,
           t.min_local_content_class AS min_local_content_class,
           t.msme_exempt_turnover AS msme_exempt_turnover,
           d.id AS department_id,
           coalesce(d.name, 'Public Procurement Authority') AS department_name,
           coalesce(m.name, 'Government Ministry') AS ministry_name,
           r.name AS region_name,
           r.state_code AS region_state_code,
           [(t)-[:IN_CATEGORY]->(wc:WorkCategory) | wc.name] AS work_categories,
           [(t)-[:REQUIRES_SPECIALIZATION]->(s:Specialization) | s.name] AS specializations,
           [(t)-[:REQUIRES_CERT]->(c:Certification) | c.name] AS certifications,
           [(t)-[:PREFERS_BRAND]->(b:Brand) | b.name] AS preferred_brands,
           [(t)-[:REQUIRES_PRODUCT]->(p:Product) | p.name] AS required_products,
           [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec.code] AS enlistment_classes
    """
    res = graph.query(query, {"tender_id": tender_id})
    if not res.result_set:
        return json.dumps({"error": f"Tender '{tender_id}' not found", "success": False})
    row = res.result_set[0]
    return json.dumps({
        "success": True,
        "tender_id": row[0],
        "title": row[1],
        "tender_amount": row[2],
        "expected_turnover_3yr": row[3],
        "min_net_worth": row[4],
        "min_solvency": row[5],
        "min_local_content_class": row[6],
        "msme_exempt_turnover": row[7],
        "department_id": row[8],
        "department_name": row[9],
        "ministry_name": row[10],
        "region_name": row[11],
        "region_state_code": row[12],
        "work_categories": row[13],
        "specializations": row[14],
        "certifications": row[15],
        "preferred_brands": row[16],
        "required_products": row[17],
        "enlistment_classes": row[18],
    }, indent=2)


@mcp.tool()
def check_client_coverage(
    client_id: str,
    tender_id: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Template Tool 2: Evaluates which statutory and capability requirement nodes are met vs unmet
    by a client for a given tender using an explainable, parameterized OpenCypher template.
    """
    graph = _get_target_graph(graph_name)
    now = int(time.time())
    query = """
    MATCH (t:Tender {id: $tender_id})
    MATCH (c:Client {id: $client_id})
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(tr:Region)<-[op:OPERATES_IN]-(c)
    WITH t, c, collect(CASE WHEN op.gst_valid = true THEN tr.name ELSE null END) AS valid_regions
    RETURN c.id AS client_id,
           c.name AS client_name,
           c.avg_turnover_3yr AS client_turnover,
           t.expected_turnover_3yr AS required_turnover,
           c.net_worth AS client_net_worth,
           t.min_net_worth AS required_net_worth,
           c.solvency AS client_solvency,
           t.min_solvency AS required_solvency,
           c.tech_staff_count AS client_tech_staff,
           t.min_tech_staff AS required_tech_staff,
           c.is_msme AS is_msme,
           t.msme_exempt_turnover AS msme_exempt_turnover,
           c.is_blacklisted AS is_blacklisted,
           c.local_content_class AS local_content_class,
           t.min_local_content_class AS required_local_content_class,
           t.status AS tender_status,
           t.deadline_at AS deadline_at,
           valid_regions,
           [(t)-[:IN_CATEGORY]->(wc:WorkCategory) | wc.name] AS required_categories,
           [(c)-[:WORKS_IN]->(wc:WorkCategory) | wc.name] AS client_categories,
           [(t)-[:REQUIRES_SPECIALIZATION]->(s:Specialization) | s.name] AS required_specializations,
           [(c)-[:HAS_SPECIALIZATION]->(s:Specialization) | s.name] AS client_specializations,
           [(t)-[:REQUIRES_CERT]->(cert:Certification) | cert.name] AS required_certifications,
           [(c)-[hc:HOLDS_CERT]->(cert:Certification) WHERE hc.valid_until IS NULL OR hc.valid_until > $now | cert.name] AS client_certifications,
           [(t)-[pb:PREFERS_BRAND]->(b:Brand) WHERE pb.strict_auth_required = true | b.name] AS required_brands,
           [(c)-[auth:AUTHORIZED_FOR]->(b:Brand)
             WHERE (auth.valid_until IS NULL OR auth.valid_until > $now)
               AND (auth.territory IN ['ALL_INDIA', 'All India'] OR auth.territory IN valid_regions
                    OR toUpper(replace(auth.territory, ' ', '_')) = 'ALL_INDIA') | b.name] AS client_brands,
           [(t)-[rp:REQUIRES_PRODUCT]->(p:Product)
             WHERE coalesce(t.oem_required, false) = true OR coalesce(rp.requires_oem_or_auth, false) = true | p.name] AS required_products,
           [(t)-[rp:REQUIRES_PRODUCT]->(p:Product)<-[sp:SUPPLIES]-(c)
             WHERE ((coalesce(rp.requires_oem_or_auth, false) = false AND coalesce(t.oem_required, false) = false) OR sp.is_oem = true)
             | p.name] AS client_products,
           [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec.code] AS required_enlistment,
           [(c)-[en:ENLISTED_AS]->(ec:EnlistmentClass) WHERE en.valid_until IS NULL OR en.valid_until > $now | ec.code] AS client_enlistment,
           c.ongoing_work_value,
           t.max_ongoing_work_allowed
    """
    res = graph.query(query, {"client_id": client_id, "tender_id": tender_id, "now": now})
    if not res.result_set:
        return json.dumps({"error": f"Client '{client_id}' or Tender '{tender_id}' not found", "success": False})
    row = res.result_set[0]
    values = {"client_id": row[0], "client_name": row[1], "client_turnover": row[2],
              "required_turnover": row[3], "client_net_worth": row[4], "required_net_worth": row[5],
              "client_solvency": row[6], "required_solvency": row[7], "client_tech_staff": row[8],
              "required_tech_staff": row[9], "is_msme": row[10], "msme_exempt_turnover": row[11],
              "is_blacklisted": row[12], "local_content_class": row[13],
              "required_local_content_class": row[14], "tender_status": row[15], "deadline_at": row[16],
              "valid_regions": row[17] or [], "required_categories": row[18] or [],
              "client_categories": row[19] or [], "required_specializations": row[20] or [],
              "client_specializations": row[21] or [], "required_certifications": row[22] or [],
              "client_certifications": row[23] or [], "required_brands": row[24] or [],
              "client_brands": row[25] or [], "required_products": row[26] or [],
              "client_products": row[27] or [], "required_enlistment": row[28] or [],
              "client_enlistment": row[29] or [], "ongoing_work_value": row[30],
              "max_ongoing_work_allowed": row[31]}

    def missing(required, held):
        held_norm = {str(value).strip().casefold() for value in held if value}
        return [value for value in required if str(value).strip().casefold() not in held_norm]

    turnover = float(values["client_turnover"] or 0.0)
    required_turnover = values["required_turnover"]
    turnover_ok = (required_turnover is None or turnover >= float(required_turnover)
                   or (values["is_msme"] is True and values["msme_exempt_turnover"] is True))
    turnover_pct = (round(turnover / float(required_turnover) * 100, 1)
                    if required_turnover not in (None, 0) else 100.0)
    region_ok = bool(values["valid_regions"])
    local_class_ok = (values["required_local_content_class"] in (None, "", "CLASS-2")
                      or values["local_content_class"] == "CLASS-1")
    deadline_ok = values["deadline_at"] is None or float(values["deadline_at"]) > now
    status_ok = values["tender_status"] in (None, "ACTIVE")

    missing_nodes = {
        "categories": missing(values["required_categories"], values["client_categories"]),
        "specializations": missing(values["required_specializations"], values["client_specializations"]),
        "certifications": missing(values["required_certifications"], values["client_certifications"]),
        "brands": missing(values["required_brands"], values["client_brands"]),
        "products": missing(values["required_products"], values["client_products"]),
        "enlistment": missing(values["required_enlistment"], values["client_enlistment"]),
    }
    gates = {
        "tender_active": {"passed": status_ok, "evidence": values["tender_status"]},
        "deadline_open": {"passed": deadline_ok, "evidence": values["deadline_at"]},
        "not_blacklisted": {"passed": values["is_blacklisted"] is False, "evidence": values["is_blacklisted"]},
        "regional_gst": {"passed": region_ok, "evidence": values["valid_regions"]},
        "turnover": {"passed": turnover_ok, "client_value": turnover,
                      "required_value": required_turnover, "coverage_pct": turnover_pct,
                      "msme_exemption_applied": bool(values["is_msme"] and values["msme_exempt_turnover"])},
        "net_worth": {"passed": values["required_net_worth"] is None or float(values["client_net_worth"] or 0) >= float(values["required_net_worth"]),
                      "client_value": values["client_net_worth"], "required_value": values["required_net_worth"]},
        "solvency": {"passed": values["required_solvency"] is None or float(values["client_solvency"] or 0) >= float(values["required_solvency"]),
                     "client_value": values["client_solvency"], "required_value": values["required_solvency"]},
        "technical_staff": {"passed": values["required_tech_staff"] is None or int(values["client_tech_staff"] or 0) >= int(values["required_tech_staff"]),
                            "client_value": values["client_tech_staff"], "required_value": values["required_tech_staff"]},
        "ongoing_work": {"passed": values["max_ongoing_work_allowed"] is None or float(values["ongoing_work_value"] or 0) <= float(values["max_ongoing_work_allowed"]),
                         "client_value": values["ongoing_work_value"], "maximum_allowed": values["max_ongoing_work_allowed"]},
        "local_content": {"passed": local_class_ok, "client_value": values["local_content_class"],
                          "required_value": values["required_local_content_class"]},
    }
    for kind, absent in missing_nodes.items():
        gates[kind] = {"passed": not absent, "missing": absent}
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    return json.dumps({
        "success": True,
        "client_id": values["client_id"],
        "client_name": values["client_name"],
        "is_eligible_solo": not failed,
        "turnover_coverage_pct": turnover_pct,
        "gates": gates,
        "met_nodes": {kind: [item for item in values[f"required_{kind}"] if item not in missing_nodes[kind]]
                      for kind in missing_nodes},
        "unmet_nodes": missing_nodes,
        "missing_requirements": failed,
        "evidence_source": "FalkorDB graph relationships and node properties",
    }, indent=2)


@mcp.tool()
def get_department_lineage(
    client_id: str,
    department_id: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Template Tool 3: Evaluates client track record and learned win-rate affinity in a procuring department
    using a parameterized OpenCypher template.
    """
    graph = _get_target_graph(graph_name)
    query = """
    MATCH (c:Client {id: $client_id})
    MATCH (d:Department {id: $department_id})
    OPTIONAL MATCH (c)-[da:DEPARTMENT_AFFINITY]->(d)
    OPTIONAL MATCH (c)-[bh:BID_HISTORY]->(past_t:Tender)<-[:ISSUED]-(d)
    RETURN d.id AS department_id,
           d.name AS department_name,
           coalesce(da.wins, 0) AS affinity_wins,
           coalesce(da.losses, 0) AS affinity_losses,
           coalesce(da.win_rate, 0.0) AS win_rate,
           coalesce(da.affinity_weight, 0.0) AS affinity_weight,
           count(bh) AS total_past_bids
    """
    res = graph.query(query, {"client_id": client_id, "department_id": department_id})
    if not res.result_set:
        return json.dumps({"department_id": department_id, "win_rate": 0.0, "affinity_weight": 0.0, "total_past_bids": 0})
    row = res.result_set[0]
    return json.dumps({
        "success": True,
        "client_id": client_id,
        "department_id": row[0],
        "department_name": row[1],
        "affinity_wins": row[2],
        "affinity_losses": row[3],
        "win_rate": row[4],
        "affinity_weight": row[5],
        "total_past_bids": row[6],
    }, indent=2)


@mcp.tool()
def find_peer_clients(
    client_id: str,
    tender_id: str,
    current_timestamp: Optional[int] = None,
    graph_name: Optional[str] = None
) -> str:
    """
    Template Tool 4: 5-Hop OpenCypher lookalike peer traversal. Traverses shared capabilities
    to discover competitors who mirror historical successful public contract winners in this
    procuring department and work category.
    Strictly groups by (peer, anchor), requires >= 2 shared capabilities per anchor,
    and requires >= 2 distinct supporting anchors.
    Shields anchor identity, contract IDs, and financial turnover from returning to the agent layer.
    """
    graph = _get_target_graph(graph_name)
    now = current_timestamp if current_timestamp is not None else int(time.time())
    query = """
    MATCH (t:Tender {id: $tender_id})-[:IN_CATEGORY]->(wc:WorkCategory)
    MATCH (t)<-[:ISSUED]-(d:Department)-[:ISSUED]->(past_t:Tender)-[:IN_CATEGORY]->(wc)
    MATCH (anchor:Client)-[:BID_HISTORY {outcome: 'WON'}]->(past_t)
    WHERE anchor.is_blacklisted = false

    MATCH (peer:Client)
    WHERE ($client_id IS NULL OR $client_id = '' OR peer.id = $client_id)
      AND peer.id <> anchor.id
      AND peer.is_blacklisted = false
      AND (t.expected_turnover_3yr IS NULL OR peer.avg_turnover_3yr >= t.expected_turnover_3yr OR (peer.is_msme = true AND t.msme_exempt_turnover = true))
      AND NOT (peer)-[:BID_HISTORY]->(:Tender)<-[:ISSUED]-(d)

    // Pattern A Gating for Peer: Regional presence, trade/category, valid certs, brands, and cooldown
    MATCH (t)-[:LOCATED_IN]->(r:Region)
    MATCH (peer)-[op:OPERATES_IN]->(r)
    WHERE op.gst_valid = true

    MATCH (peer)-[:WORKS_IN]->(wc)

    OPTIONAL MATCH (t)-[:REQUIRES_CERT]->(req_cert:Certification)
    OPTIONAL MATCH (peer)-[hc:HOLDS_CERT]->(req_cert)
      WHERE hc.valid_until IS NULL OR hc.valid_until > $now
    WITH t, d, past_t, anchor, peer, r,
         count(DISTINCT req_cert) AS total_req_certs,
         count(DISTINCT hc) AS held_req_certs
    WHERE total_req_certs = 0 OR held_req_certs = total_req_certs

    OPTIONAL MATCH (t)-[:PREFERS_BRAND]->(req_brand:Brand)
    OPTIONAL MATCH (peer)-[auth:AUTHORIZED_FOR]->(req_brand)
      WHERE (auth.territory = r.name OR toUpper(replace(auth.territory, ' ', '_')) = 'ALL_INDIA') AND (auth.valid_until IS NULL OR auth.valid_until > $now)
    WITH t, d, past_t, anchor, peer,
         count(DISTINCT req_brand) AS total_req_brands,
         count(DISTINCT auth) AS held_req_brands
    WHERE total_req_brands = 0 OR held_req_brands = total_req_brands

    WITH t, d, past_t, anchor, peer,
         [(peer)-[eval:MATCHED_TENDER]->(t)
          WHERE eval.status IN ['WON', 'LOST']
             OR (eval.status = 'ALERTED' AND ($now - eval.last_alert_sent) < 172800) | eval] AS blocked_evals
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

    RETURN peer.id AS peer_client_id,
           peer.name AS peer_name,
           supporting_anchors,
           total_shared_caps,
           round((CASE WHEN raw_score > 0.92 THEN 0.92 ELSE raw_score END) * 10000.0) / 10000.0 AS match_score
    ORDER BY supporting_anchors DESC, total_shared_caps DESC
    LIMIT 5
    """
    res = graph.query(query, {"client_id": client_id, "tender_id": tender_id, "now": now})
    peers = []
    for r in res.result_set:
        peer_id = r[0]
        peer_name = r[1]
        supporting_anchors = int(r[2])
        shared_caps_count = int(r[3])
        match_score = float(r[4])

        plus_points = [
            f"Historical capability signal: {shared_caps_count} shared capability links across {supporting_anchors} qualifying winner anchors.",
            "Tender alignment: peer has a matching work category and valid GST relationship for the tender region.",
            "Privacy: historical anchor identities and past tender references are withheld from this result.",
        ]

        peers.append({
            "peer_id": peer_id,
            "peer_name": peer_name,
            "benchmark_reference": "[Generic Peer Benchmark - Identity Shielded]",
            "supporting_anchors": supporting_anchors,
            "shared_capabilities_count": shared_caps_count,
            "match_score": match_score,
            "plus_points": plus_points,
        })

    return json.dumps({
        "success": True,
        "tender_id": tender_id,
        "target_client_id": client_id,
        "peer_count": len(peers),
        "peers": peers,
    }, indent=2)


@mcp.tool()
def explore_paths(
    spec_json: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Template Tool 5: Constrained graph exploration tool.
    The agent supplies a structured spec JSON, and the server validates labels & edges
    against white-listed schemas, executing a safe parameterized Cypher query.
    """
    spec = json.loads(spec_json) if isinstance(spec_json, str) else spec_json
    start_type = spec.get("start_type", "Client")
    start_id = spec.get("start_id", "")
    target_type = spec.get("target_type", "Tender")
    target_id = spec.get("target_id", "")

    allowed_nodes = {"Client", "Tender", "Department", "Ministry", "WorkCategory", "Specialization", "Certification", "Brand", "Product", "Region", "EnlistmentClass"}
    if start_type not in allowed_nodes or target_type not in allowed_nodes:
        return json.dumps({"error": f"Invalid node type in spec. Allowed: {list(allowed_nodes)}", "success": False})

    graph = _get_target_graph(graph_name)
    query = """
    MATCH (s), (t)
    WHERE any(l IN labels(s) WHERE l = $start_type)
      AND any(l IN labels(t) WHERE l = $target_type)
      AND $start_id IN [s.id, s.name, s.code]
      AND $target_id IN [t.id, t.name, t.code]
    WITH s, t
    WITH shortestPath((s)-[*..3]->(t)) AS path_fwd, shortestPath((t)-[*..3]->(s)) AS path_rev
    WITH coalesce(path_fwd, path_rev) AS path
    WHERE path IS NOT NULL
      AND NONE(r IN relationships(path) WHERE type(r) IN ['BID_HISTORY', 'MATCHED_TENDER'])
    RETURN [n IN nodes(path) | {id: coalesce(n.id, n.name, n.code), label: labels(n)[0]}] AS path_nodes,
           [r IN relationships(path) | type(r)] AS path_relationships
    LIMIT 5
    """
    res = graph.query(query, {
        "start_type": start_type,
        "start_id": start_id,
        "target_type": target_type,
        "target_id": target_id,
    })
    results = []
    for r in res.result_set:
        results.append({
            "nodes": r[0],
            "relationships": r[1]
        })
    return json.dumps({
        "success": True,
        "paths_found": len(results),
        "paths": results,
    }, indent=2)


@mcp.tool()
def get_client_and_tender_for_email(
    client_id: str,
    tender_id: str,
    graph_name: Optional[str] = None
) -> str:
    """
    Fetches comprehensive client profile, tender requirements, and alert match data
    specifically required by the Communication Agent to draft tailored alerting emails.
    Strictly pulls client email directly from the respective (:Client) node in FalkorDB.
    """
    graph = _get_target_graph(graph_name)
    query = """
    MATCH (c:Client {id: $client_id})
    MATCH (t:Tender {id: $tender_id})
    OPTIONAL MATCH (c)-[m:MATCHED_TENDER]->(t)
    OPTIONAL MATCH (ad:AgentDecision)-[:FOR_CLIENT]->(c)
    WHERE (ad)-[:EVALUATED_TENDER]->(t)
    WITH c, t, m, ad
    ORDER BY ad.created_at DESC
    WITH c, t, m, head(collect(ad)) AS latest_ad
    OPTIONAL MATCH (d:Department)-[:ISSUED]->(t)
    OPTIONAL MATCH (min:Ministry)-[:HAS_DEPARTMENT]->(d)
    OPTIONAL MATCH (r:Region)<-[:LOCATED_IN]-(t)
    RETURN c.id AS client_id,
           c.name AS client_name,
           c.email AS client_email,
           c.avg_turnover_3yr AS client_turnover,
           c.is_msme AS is_msme,
           t.id AS tender_id,
           t.title AS tender_title,
           t.tender_amount AS tender_amount,
           t.deadline_at AS tender_deadline,
           t.listed_date AS listed_date,
           t.source_portal AS source_portal,
           d.name AS department_name,
           min.name AS ministry_name,
           r.name AS region_name,
           [(t)-[:IN_CATEGORY]->(wc:WorkCategory) | wc.name] AS work_categories,
           [(c)-[:HOLDS_CERT]->(cert:Certification) | cert.name] AS client_certs,
           [(c)-[:AUTHORIZED_FOR]->(b:Brand) | b.name] AS client_brands,
           m.match_score AS match_score,
           m.match_type AS match_type,
           latest_ad.reasoning_trace AS reasoning_trace,
           latest_ad.path_summary AS path_summary
    """
    res = graph.query(query, {"client_id": client_id, "tender_id": tender_id})
    if not res.result_set:
        return json.dumps({"error": f"Client {client_id} or Tender {tender_id} not found", "found": False})

    row = res.result_set[0]
    data = {
        "found": True,
        "client": {
            "id": row[0],
            "name": row[1],
            "email": row[2],  # Strictly pulled from the (:Client) node in FalkorDB
            "turnover_3yr": row[3],
            "is_msme": row[4],
            "certifications": row[15] or [],
            "brands": row[16] or [],
        },
        "tender": {
            "id": row[5],
            "title": row[6],
            "amount": row[7],
            "deadline_at": row[8],
            "listed_date": row[9],
            "source_portal": row[10],
            "department": row[11],
            "ministry": row[12],
            "region": row[13],
            "work_categories": row[14] or [],
        },
        "match": {
            "score": row[17],
            "type": row[18],
            "reasoning_trace": row[19] or "",
            "path_summary": row[20] or "",
        }
    }
    return json.dumps(data, indent=2)


if __name__ == "__main__":
    mcp.run()


