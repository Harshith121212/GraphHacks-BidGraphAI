"""Rich multi-hop Indian tender and client graph seeder for FalkorDB using actual GeM and CPPP tenders.

DISCLAIMER: All contractor client identities, financial balances, and brand authorizations
in this seeder are synthetic demonstration records created for hackathon benchmarking purposes.
"""

import os
import sys
import json
import logging
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from falkordb import Graph
from db.connection import get_graph
from db.schema import initialize_schema
from pipeline.enricher_ingestor import EnricherIngestor

logger = logging.getLogger(__name__)


def seed_jv_demo_fixture(graph: Graph) -> None:
    """Idempotently add the synthetic JV demo tender requirements and clients."""
    graph.query("""
    MERGE (:Region {name: 'Maharashtra', state_code: 'MH'})
    MERGE (:Region {name: 'Karnataka', state_code: 'KA'})
    MERGE (:WorkCategory {name: 'Civil Works'})
    MERGE (:WorkCategory {name: 'Electrical'})
    MERGE (:Specialization {name: 'Civil Contractor'})
    MERGE (:Specialization {name: 'Wire Manufacturing Facility'})
    MERGE (:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL'})
    MERGE (:Certification {name: 'BIS IS-7098'})
    MERGE (:Certification {name: 'CPWD'})
    MERGE (:Certification {name: 'IS 1786'})
    MERGE (:Brand {name: 'Havells'})
    MERGE (:Product {name: 'LT/HT Armoured Cables'})
    MERGE (:Product {name: 'PCC M20 foundation and plinth'})
    MERGE (:Product {name: 'Reinforcement steel Fe500D'})
    """)

    graph.query("""
    MATCH (t:Tender {id: 'RW/NH-12014/ 04/2025-MAH/ZONE-IV'})
    SET t.expected_turnover_3yr = 280000000.0,
        t.min_net_worth = 30000000.0,
        t.min_solvency = 40000000.0,
        t.min_tech_staff = 10,
        t.min_local_content_class = 'CLASS-1',
        t.max_ongoing_work_allowed = 28600000.0,
        t.oem_required = false
    WITH t
    MATCH (wc_civ:WorkCategory {name: 'Civil Works'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_civ:Specialization {name: 'Civil Contractor'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (ec_civ:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})
    MATCH (p_pcc:Product {name: 'PCC M20 foundation and plinth'})
    MATCH (p_steel:Product {name: 'Reinforcement steel Fe500D'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (c_cpwd:Certification {name: 'CPWD'})
    MATCH (c_is1786:Certification {name: 'IS 1786'})
    MERGE (t)-[:IN_CATEGORY]->(wc_civ)
    MERGE (t)-[:IN_CATEGORY]->(wc_elec)
    MERGE (t)-[:REQUIRES_SPECIALIZATION]->(s_civ)
    MERGE (t)-[:REQUIRES_SPECIALIZATION]->(s_wire)
    MERGE (t)-[:REQUIRES_ENLISTMENT]->(ec_civ)
    MERGE (t)-[:PREFERS_BRAND {strict_auth_required: true}]->(b_hav)
    MERGE (t)-[:REQUIRES_PRODUCT {quantity: 2000, unit: 'METERS', requires_oem_or_auth: false}]->(p_cab)
    MERGE (t)-[:REQUIRES_PRODUCT {quantity: 1467, unit: 'Cum', requires_oem_or_auth: false}]->(p_pcc)
    MERGE (t)-[:REQUIRES_PRODUCT {quantity: 110091, unit: 'Kg', requires_oem_or_auth: false}]->(p_steel)
    MERGE (t)-[:REQUIRES_CERT]->(c_bis)
    MERGE (t)-[:REQUIRES_CERT]->(c_cpwd)
    MERGE (t)-[:REQUIRES_CERT]->(c_is1786)
    """)

    civil_profiles = [
        {
            "id": "client_demo_civil_northstar",
            "name": "Northstar Civil Works (Synthetic Demo)",
            "email": "northstar-demo@example.invalid",
            "founded_date": "2018-04-12",
            "legal_form": "PRIVATE_LIMITED",
            "turnover_fy24": 135000000.0,
            "turnover_fy25": 150000000.0,
            "turnover_fy26": 165000000.0,
            "avg_turnover_3yr": 150000000.0,
            "net_worth": 25000000.0,
            "solvency": 30000000.0,
            "ongoing_work_value": 10000000.0,
            "is_msme": True,
            "is_startup": False,
            "local_content_class": "CLASS-1",
            "is_blacklisted": False,
            "tech_staff_count": 24,
            "portal_seller_id": "DEMO-NORTHSTAR-001",
            "data_origin": "SYNTHETIC_DEMO",
        },
        {
            "id": "client_demo_civil_riverstone",
            "name": "Riverstone Infrastructure (Synthetic Demo)",
            "email": "riverstone-demo@example.invalid",
            "founded_date": "2017-09-03",
            "legal_form": "PRIVATE_LIMITED",
            "turnover_fy24": 145000000.0,
            "turnover_fy25": 155000000.0,
            "turnover_fy26": 165000000.0,
            "avg_turnover_3yr": 155000000.0,
            "net_worth": 27000000.0,
            "solvency": 32000000.0,
            "ongoing_work_value": 12000000.0,
            "is_msme": False,
            "is_startup": False,
            "local_content_class": "CLASS-1",
            "is_blacklisted": False,
            "tech_staff_count": 27,
            "portal_seller_id": "DEMO-RIVERSTONE-002",
            "data_origin": "SYNTHETIC_DEMO",
        },
    ]
    for profile in civil_profiles:
        graph.query("""
        MATCH (wc:WorkCategory {name: 'Civil Works'})
        MATCH (spec:Specialization {name: 'Civil Contractor'})
        MATCH (enlist:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL'})
        MATCH (bis:Certification {name: 'BIS IS-7098'})
        MATCH (cpwd:Certification {name: 'CPWD'})
        MATCH (is1786:Certification {name: 'IS 1786'})
        MERGE (c:Client {id: $client_id})
        SET c += $profile
        MERGE (c)-[:WORKS_IN]->(wc)
        MERGE (c)-[:HAS_SPECIALIZATION]->(spec)
        MERGE (c)-[:HOLDS_CERT {valid_until: 1893456000}]->(bis)
        MERGE (c)-[:HOLDS_CERT {valid_until: 1893456000}]->(cpwd)
        MERGE (c)-[:HOLDS_CERT {valid_until: 1893456000}]->(is1786)
        MERGE (c)-[:ENLISTED_AS {grade: 'Class I', valid_until: 1893456000}]->(enlist)
        """, {"client_id": profile["id"], "profile": profile})

    electrical_profiles = [
        {
            "id": "client_demo_electrical_voltcraft",
            "name": "Voltcraft Power Systems (Synthetic Demo)",
            "email": "voltcraft-demo@example.invalid",
            "founded_date": "2019-02-18",
            "legal_form": "PRIVATE_LIMITED",
            "turnover_fy24": 135000000.0,
            "turnover_fy25": 150000000.0,
            "turnover_fy26": 165000000.0,
            "avg_turnover_3yr": 150000000.0,
            "net_worth": 25000000.0,
            "solvency": 30000000.0,
            "ongoing_work_value": 10000000.0,
            "is_msme": True,
            "is_startup": False,
            "local_content_class": "CLASS-1",
            "is_blacklisted": False,
            "tech_staff_count": 24,
            "portal_seller_id": "DEMO-VOLTCRAFT-003",
            "data_origin": "SYNTHETIC_DEMO",
        },
        {
            "id": "client_demo_electrical_sparkline",
            "name": "Sparkline Electrical Manufacturing (Synthetic Demo)",
            "email": "sparkline-demo@example.invalid",
            "founded_date": "2016-11-07",
            "legal_form": "PRIVATE_LIMITED",
            "turnover_fy24": 145000000.0,
            "turnover_fy25": 155000000.0,
            "turnover_fy26": 165000000.0,
            "avg_turnover_3yr": 155000000.0,
            "net_worth": 27000000.0,
            "solvency": 32000000.0,
            "ongoing_work_value": 12000000.0,
            "is_msme": False,
            "is_startup": False,
            "local_content_class": "CLASS-1",
            "is_blacklisted": False,
            "tech_staff_count": 27,
            "portal_seller_id": "DEMO-SPARKLINE-004",
            "data_origin": "SYNTHETIC_DEMO",
        },
    ]
    for profile in electrical_profiles:
        graph.query("""
        MATCH (wc:WorkCategory {name: 'Electrical'})
        MATCH (spec:Specialization {name: 'Wire Manufacturing Facility'})
        MATCH (bis:Certification {name: 'BIS IS-7098'})
        MATCH (brand:Brand {name: 'Havells'})
        MATCH (cable:Product {name: 'LT/HT Armoured Cables'})
        MERGE (c:Client {id: $client_id})
        SET c += $profile
        MERGE (c)-[:WORKS_IN]->(wc)
        MERGE (c)-[:HAS_SPECIALIZATION]->(spec)
        MERGE (c)-[:HOLDS_CERT {valid_until: 1893456000}]->(bis)
        MERGE (c)-[:AUTHORIZED_FOR {role: 'Authorized Vendor', territory: 'All India', valid_until: 1893456000}]->(brand)
        MERGE (c)-[:SUPPLIES {is_oem: false, facility_name: 'Synthetic Demo Cable Unit', monthly_capacity: 30000}]->(cable)
        """, {"client_id": profile["id"], "profile": profile})

    graph.query("""
    MATCH (c:Client)
    WHERE c.id IN [
      'client_demo_civil_northstar', 'client_demo_civil_riverstone',
      'client_demo_electrical_voltcraft', 'client_demo_electrical_sparkline'
    ]
    UNWIND ['Maharashtra', 'Karnataka', 'Delhi', 'Uttar Pradesh', 'Assam',
            'West Bengal', 'Tamil Nadu', 'Gujarat', 'Rajasthan', 'Himachal Pradesh',
            'Madhya Pradesh', 'Uttarakhand'] AS region_name
    MERGE (r:Region {name: region_name})
    MERGE (c)-[:OPERATES_IN {gst_valid: true, filing_status: 'ACTIVE'}]->(r)
    """)


def seed_database(graph_name: Optional[str] = None, clear_existing: bool = True) -> Dict[str, Any]:
    """
    Populates FalkorDB with real Indian government procurement tenders (scraped from GeM & CPPP)
    and an expanded roster of 16 diverse Indian contractor clients covering:
    Electrical EPC, Heavy Civil, Road Construction, IT Hardware, HVAC, Furniture, Healthcare,
    and MSME Manufacturing.
    """
    graph: Graph = get_graph(graph_name)

    # Memory Survival Check: if not explicitly forcing a clear, check for existing SystemMeta marker
    if not clear_existing:
        try:
            check_res = graph.query("MATCH (sm:SystemMeta {key: 'scraper_status'}) RETURN sm.total_tenders_ingested").result_set
            if check_res and len(check_res) > 0:
                seed_jv_demo_fixture(graph)
                logger.info("SystemMeta marker found in FalkorDB; graph already initialized. Preserving memory across cold start.")
                return {
                    "status": "preserved_with_demo_fixture",
                    "message": "Existing graph and learned memory preserved; synthetic JV demo profiles and requirements upserted.",
                    "total_tenders": check_res[0][0] if check_res[0] else 26,
                }
        except Exception as exc:
            logger.debug("Could not verify existing SystemMeta marker: %s", exc)

    if clear_existing:
        try:
            graph.delete()
            logger.info("Cleared existing graph database.")
        except Exception as exc:
            logger.warning("Could not delete graph (may not exist yet): %s", exc)

    # 1. Initialize schema indexes and constraints
    schema_res = initialize_schema(graph)

    # 2. System Metadata Node (Scraper Heartbeat)
    graph.query("""
    MERGE (sm:SystemMeta {key: 'scraper_status'})
    SET sm.last_scraped_at = 1718000000,
        sm.total_tenders_ingested = 26,
        sm.scraper_source = 'gem_and_cppp_portal'
    """)

    # 3. Discrete Shared Entities
    # Ministries & Core Departments
    graph.query("""
    MERGE (m_pow:Ministry {id: 'min_power'}) ON CREATE SET m_pow.name = 'Ministry of Power'
    MERGE (m_rail:Ministry {id: 'min_rail'}) ON CREATE SET m_rail.name = 'Ministry of Railways'
    MERGE (m_morth:Ministry {id: 'min_morth'}) ON CREATE SET m_morth.name = 'Ministry of Road Transport and Highways'
    MERGE (m_urb:Ministry {id: 'min_urban'}) ON CREATE SET m_urb.name = 'Ministry of Housing and Urban Affairs'
    MERGE (m_def:Ministry {id: 'min_defence'}) ON CREATE SET m_def.name = 'Ministry of Defence'

    MERGE (d_ntpc:Department {id: 'dept_ntpc', ministry_id: 'min_power'}) ON CREATE SET d_ntpc.name = 'NTPC Karnataka Region'
    MERGE (d_swr:Department {id: 'dept_swr', ministry_id: 'min_rail'}) ON CREATE SET d_swr.name = 'South Western Railway (SWR)'
    MERGE (d_nhai:Department {id: 'dept_nhai', ministry_id: 'min_morth'}) ON CREATE SET d_nhai.name = 'NHAI National Highways Division'
    MERGE (d_cpwd:Department {id: 'dept_cpwd', ministry_id: 'min_urban'}) ON CREATE SET d_cpwd.name = 'CPWD Southern Zone'

    MERGE (m_pow)-[:HAS_DEPARTMENT]->(d_ntpc)
    MERGE (m_rail)-[:HAS_DEPARTMENT]->(d_swr)
    MERGE (m_morth)-[:HAS_DEPARTMENT]->(d_nhai)
    MERGE (m_urb)-[:HAS_DEPARTMENT]->(d_cpwd)
    """)

    # Regions
    graph.query("""
    MERGE (:Region {name: 'Karnataka', state_code: 'KA'})
    MERGE (:Region {name: 'Maharashtra', state_code: 'MH'})
    MERGE (:Region {name: 'Delhi', state_code: 'DL'})
    MERGE (:Region {name: 'Uttar Pradesh', state_code: 'UP'})
    MERGE (:Region {name: 'Assam', state_code: 'AS'})
    MERGE (:Region {name: 'West Bengal', state_code: 'WB'})
    MERGE (:Region {name: 'Tamil Nadu', state_code: 'TN'})
    MERGE (:Region {name: 'Gujarat', state_code: 'GJ'})
    MERGE (:Region {name: 'Rajasthan', state_code: 'RJ'})
    MERGE (:Region {name: 'Andhra Pradesh', state_code: 'AP'})
    MERGE (:Region {name: 'Telangana', state_code: 'TG'})
    MERGE (:Region {name: 'Uttarakhand', state_code: 'UK'})
    MERGE (:Region {name: 'Himachal Pradesh', state_code: 'HP'})
    MERGE (:Region {name: 'Madhya Pradesh', state_code: 'MP'})
    """)

    # Work Categories
    graph.query("""
    MERGE (:WorkCategory {name: 'Electrical'})
    MERGE (:WorkCategory {name: 'Civil Works'})
    MERGE (:WorkCategory {name: 'IT Hardware'})
    MERGE (:WorkCategory {name: 'Furniture'})
    MERGE (:WorkCategory {name: 'Medical Equipment'})
    MERGE (:WorkCategory {name: 'Water Supply'})
    MERGE (:WorkCategory {name: 'Railway Track Items'})
    MERGE (:WorkCategory {name: 'Housekeeping Services'})
    MERGE (:WorkCategory {name: 'Solar EPC'})
    MERGE (:WorkCategory {name: 'Steel'})
    """)

    # Specializations
    graph.query("""
    MERGE (:Specialization {name: 'Wire Manufacturing Facility'})
    MERGE (:Specialization {name: 'HT Substation Erection'})
    MERGE (:Specialization {name: 'Civil Contractor'})
    MERGE (:Specialization {name: 'Highway EPC'})
    MERGE (:Specialization {name: 'Office Modular Furnishing'})
    MERGE (:Specialization {name: 'Server Network Engineering'})
    MERGE (:Specialization {name: 'HVAC Air Conditioning'})
    MERGE (:Specialization {name: 'Biomedical Waste Management'})
    MERGE (:Specialization {name: 'Structural Fabrication'})
    MERGE (:Specialization {name: 'Solar PV Farm Erection'})
    """)

    # Certifications
    graph.query("""
    MERGE (:Certification {name: 'BIS IS-7098'})
    MERGE (:Certification {name: 'ISO 9001:2015'})
    MERGE (:Certification {name: 'ISO 27001'})
    MERGE (:Certification {name: 'ISO 13485'})
    MERGE (:Certification {name: 'NABL Accredited'})
    MERGE (:Certification {name: 'BIFMA Level 3'})
    MERGE (:Certification {name: 'IS 1786'})
    MERGE (:Certification {name: 'CPWD Class 1'})
    MERGE (:Certification {name: 'BEE 5-Star Energy'})
    MERGE (:Certification {name: 'CDSCO Licensed'})
    """)

    # Brands (Simulated benchmark preference categories)
    graph.query("""
    MERGE (:Brand {name: 'Havells', is_demo_sample: true})
    MERGE (:Brand {name: 'Polycab', is_demo_sample: true})
    MERGE (:Brand {name: 'ABB', is_demo_sample: true})
    MERGE (:Brand {name: 'Schneider Electric', is_demo_sample: true})
    MERGE (:Brand {name: 'HP', is_demo_sample: true})
    MERGE (:Brand {name: 'Dell', is_demo_sample: true})
    MERGE (:Brand {name: 'Cisco', is_demo_sample: true})
    MERGE (:Brand {name: 'Voltas', is_demo_sample: true})
    MERGE (:Brand {name: 'Blue Star', is_demo_sample: true})
    MERGE (:Brand {name: 'Godrej Interio', is_demo_sample: true})
    MERGE (:Brand {name: 'Nilkamal', is_demo_sample: true})
    MERGE (:Brand {name: 'Philips Healthcare', is_demo_sample: true})
    """)

    # Products
    graph.query("""
    MERGE (:Product {name: 'LT/HT Armoured Cables', category: 'Electrical'})
    MERGE (:Product {name: 'Industrial Switchgear', category: 'Electrical'})
    MERGE (:Product {name: 'FRLS Copper Cable 2.5 sq mm', category: 'Electrical'})
    MERGE (:Product {name: 'LED Panel Luminaire 36 W', category: 'Electrical'})
    MERGE (:Product {name: 'VRV/VRF Air Conditioning System', category: 'Electrical'})
    MERGE (:Product {name: 'Desktop Computers', category: 'IT Hardware'})
    MERGE (:Product {name: 'Enterprise Servers', category: 'IT Hardware'})
    MERGE (:Product {name: 'Ergonomic Office Furniture', category: 'Furniture'})
    MERGE (:Product {name: 'Compactor Storage System', category: 'Furniture'})
    MERGE (:Product {name: 'Structural Steel Girders', category: 'Steel'})
    MERGE (:Product {name: 'Reinforcement Steel Fe500D', category: 'Civil Works'})
    MERGE (:Product {name: 'PCC M20 Foundation and Plinth', category: 'Civil Works'})
    MERGE (:Product {name: 'Biomedical Waste Collection Bags', category: 'Medical Equipment'})
    """)

    # Enlistment Classes
    graph.query("""
    MERGE (:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL', authority: 'CPWD', grade: 'Class I', value_limit: 500000000.0})
    MERGE (:EnlistmentClass {code: 'CPWD-CLASS-II-ELECT', authority: 'CPWD', grade: 'Class II', value_limit: 100000000.0})
    MERGE (:EnlistmentClass {code: 'RAIL-CLASS-A', authority: 'Indian Railways', grade: 'Class A', value_limit: 250000000.0})
    MERGE (:EnlistmentClass {code: 'NHAI-SUPER-CLASS', authority: 'NHAI', grade: 'Super Class', value_limit: 1000000000.0})
    """)

    # 4. Ingest Actual Scraped Tenders from GeM & CPPP
    ingestor = EnricherIngestor(graph_name=graph_name)
    data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tenders_enriched.jsonl")

    ingested_count = 0
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    enriched = ingestor.enrich_tender(record)
                    ingestor.upsert_tender(enriched, graph=graph)
                    ingested_count += 1
                except Exception as exc:
                    logger.warning("Error seeding scraped tender: %s", exc)
    logger.info("Ingested %d actual scraped tenders from %s", ingested_count, data_file)

    # 5. Seed Historical Won Tender to anchor 5-Hop Lookalike Peer Traversals
    # (CPPP/NRL/POLY/2024/01 awarded to client_apex in Numaligarh Refinery / HURL Central Utilities)
    graph.query("""
    MERGE (m_pow:Ministry {id: 'min_power'}) ON CREATE SET m_pow.name = 'Ministry of Power'
    MERGE (d_hurl:Department {id: 'dept_hurl', ministry_id: 'min_power'})
    ON CREATE SET d_hurl.name = 'HURL & Central Power Utilities'
    MERGE (m_pow)-[:HAS_DEPARTMENT]->(d_hurl)

    MERGE (r_mh:Region {name: 'Maharashtra'})
    MERGE (wc_elec:WorkCategory {name: 'Electrical'})
    MERGE (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MERGE (c_bis:Certification {name: 'BIS IS-7098'})
    MERGE (b_hav:Brand {name: 'Havells'})
    MERGE (p_cab:Product {name: 'LT/HT Armoured Cables'})

    MERGE (t_past:Tender {
        id: 'CPPP/NRL/POLY/2024/01',
        title: 'Numaligarh Refinery E-House Package & 33kV Substation Line Package',
        reference_no: 'NRL/POLY/ELEC/2024/01',
        tender_amount: 85000000.0,
        expected_turnover_3yr: 50000000.0,
        min_net_worth: 10000000.0,
        min_solvency: 15000000.0,
        max_ongoing_work_allowed: 100000000.0,
        oem_required: true,
        min_local_content_class: 'CLASS-1',
        min_tech_staff: 15,
        msme_exempt_turnover: false,
        status: 'AWARDED',
        published_at: 1685000000,
        deadline_at: 1689000000,
        scraped_at: '2026-10-10T11:00:00+05:30',
        source_portal: 'CPPP',
        listed_date: '2024-05-25',
        tender_url: 'https://eprocure.gov.in/eprocure/app'
    })
    MERGE (d_hurl)-[:ISSUED]->(t_past)
    MERGE (t_past)-[:LOCATED_IN]->(r_mh)
    MERGE (t_past)-[:IN_CATEGORY]->(wc_elec)
    MERGE (t_past)-[:REQUIRES_SPECIALIZATION]->(s_wire)
    MERGE (t_past)-[:REQUIRES_CERT]->(c_bis)
    MERGE (t_past)-[:PREFERS_BRAND {strict_auth_required: true}]->(b_hav)
    MERGE (t_past)-[:REQUIRES_PRODUCT {quantity: 6000, unit: 'METERS', requires_oem_or_auth: true}]->(p_cab)

    // Second Historical Won Tender under dept_hurl in same WorkCategory (Electrical)
    MERGE (t_past2:Tender {
        id: 'CPPP/HURL/ELECTRICAL/2024/02',
        title: 'HURL Sindri Substation Electrical Distribution & Cabling Package',
        reference_no: 'HURL/SINDRI/ELECT/2024/02',
        tender_amount: 92000000.0,
        expected_turnover_3yr: 60000000.0,
        min_net_worth: 15000000.0,
        min_solvency: 20000000.0,
        max_ongoing_work_allowed: 120000000.0,
        oem_required: true,
        min_local_content_class: 'CLASS-1',
        min_tech_staff: 20,
        msme_exempt_turnover: false,
        status: 'AWARDED',
        published_at: 1686000000,
        deadline_at: 1690000000,
        scraped_at: '2026-10-10T11:00:00+05:30',
        source_portal: 'CPPP',
        listed_date: '2024-06-15',
        tender_url: 'https://eprocure.gov.in/eprocure/app'
    })
    MERGE (d_hurl)-[:ISSUED]->(t_past2)
    MERGE (t_past2)-[:LOCATED_IN]->(r_mh)
    MERGE (t_past2)-[:IN_CATEGORY]->(wc_elec)
    MERGE (t_past2)-[:REQUIRES_SPECIALIZATION]->(s_wire)
    MERGE (t_past2)-[:REQUIRES_CERT]->(c_bis)
    MERGE (t_past2)-[:PREFERS_BRAND {strict_auth_required: true}]->(b_hav)
    MERGE (t_past2)-[:REQUIRES_PRODUCT {quantity: 5000, unit: 'METERS', requires_oem_or_auth: true}]->(p_cab)
    """)

    # Connect the primary active CPPP electrical tenders to Havells brand, wire specialization,
    # and dept_hurl so lookalike peer discovery executes natively on actual 5-hop graph connections
    graph.query("""
    MATCH (t:Tender)
    WHERE t.id IN ['IWD/IE/26-27/RT2/E-49', 'H/G/CNM/26-27/26P158/TE-206']
    MATCH (d_hurl:Department {id: 'dept_hurl'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})
    MATCH (ec_elec:EnlistmentClass {code: 'CPWD-CLASS-II-ELECT'})
    MERGE (d_hurl)-[:ISSUED]->(t)
    MERGE (t)-[:PREFERS_BRAND {strict_auth_required: true}]->(b_hav)
    MERGE (t)-[:REQUIRES_SPECIALIZATION]->(s_wire)
    MERGE (t)-[:REQUIRES_CERT]->(c_bis)
    MERGE (t)-[:REQUIRES_PRODUCT {quantity: 3500, unit: 'METERS', requires_oem_or_auth: true}]->(p_cab)
    MERGE (t)-[:REQUIRES_ENLISTMENT]->(ec_elec)
    SET t.oem_required = true
    """)

    # Connect the primary active heavy civil/highway tender to CPWD-CLASS-I-CIVIL
    # and Electrical requirements to trigger JV consortium matching
    graph.query("""
    MATCH (t:Tender)
    WHERE t.id = 'RW/NH-12014/ 04/2025-MAH/ZONE-IV'
    MATCH (wc_civ:WorkCategory {name: 'Civil Works'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_civ:Specialization {name: 'Civil Contractor'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (ec_civ:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MERGE (t)-[:IN_CATEGORY]->(wc_civ)
    MERGE (t)-[:IN_CATEGORY]->(wc_elec)
    MERGE (t)-[:REQUIRES_SPECIALIZATION]->(s_civ)
    MERGE (t)-[:REQUIRES_SPECIALIZATION]->(s_wire)
    MERGE (t)-[:REQUIRES_ENLISTMENT]->(ec_civ)
    MERGE (t)-[:PREFERS_BRAND {strict_auth_required: true}]->(b_hav)
    MERGE (t)-[:REQUIRES_PRODUCT {quantity: 2000, unit: 'METERS', requires_oem_or_auth: false}]->(p_cab)
    MERGE (t)-[:REQUIRES_CERT]->(c_bis)
    SET t.expected_turnover_3yr = 280000000.0,
        t.min_net_worth = 30000000.0,
        t.min_solvency = 40000000.0
    """)

    # 6. Seed Expanded Client Roster (12 Comprehensive Indian Contractors)

    # Client 1: Surya Wire & Switchgear Pvt Ltd (Electrical & Cabling)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})
    MATCH (ec_elec:EnlistmentClass {code: 'CPWD-CLASS-II-ELECT'})

    MERGE (c_surya:Client {
        id: 'client_surya',
        name: 'Surya Wire & Switchgear Pvt Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2016-08-20',
        legal_form: 'PRIVATE_LIMITED',
        turnover_fy24: 85000000.0,
        turnover_fy25: 95000000.0,
        turnover_fy26: 105000000.0,
        avg_turnover_3yr: 95000000.0,
        net_worth: 38000000.0,
        solvency: 45000000.0,
        ongoing_work_value: 12000000.0,
        is_msme: true,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 28,
        portal_seller_id: 'SURYA-GEM-002'
    })
    MERGE (c_surya)-[:WORKS_IN]->(wc_elec)
    MERGE (c_surya)-[:HAS_SPECIALIZATION]->(s_wire)
    MERGE (c_surya)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bis)
    MERGE (c_surya)-[:AUTHORIZED_FOR {role: 'Authorized Vendor', territory: 'All India', valid_until: 1893456000}]->(b_hav)
    MERGE (c_surya)-[:SUPPLIES {is_oem: true, facility_name: 'Bengaluru Wire Unit', monthly_capacity: 50000}]->(p_cab)
    MERGE (c_surya)-[:ENLISTED_AS {grade: 'Class II', valid_until: 1893456000}]->(ec_elec)
    MERGE (c_surya)-[:OPERATES_IN {gstin: '29BBBBB2222B1Z5', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_surya)-[:OPERATES_IN {gstin: '27BBBBB2222B1Z4', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    """)

    # Client 2: Apex Electricals & Cables Ltd (Experienced Bidder, Past Winner)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (s_ht:Specialization {name: 'HT Substation Erection'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (b_poly:Brand {name: 'Polycab'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})
    MATCH (ec_elec:EnlistmentClass {code: 'CPWD-CLASS-II-ELECT'})
    MATCH (d_hurl:Department {id: 'dept_hurl'})
    MATCH (t_past:Tender {id: 'CPPP/NRL/POLY/2024/01'})

    MERGE (c_apex:Client {
        id: 'client_apex',
        name: 'Apex Electricals & Cables Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2010-04-15',
        legal_form: 'PUBLIC_LIMITED',
        turnover_fy24: 110000000.0,
        turnover_fy25: 120000000.0,
        turnover_fy26: 130000000.0,
        avg_turnover_3yr: 120000000.0,
        net_worth: 40000000.0,
        solvency: 60000000.0,
        ongoing_work_value: 20000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 45,
        portal_seller_id: 'APEX-GEM-001'
    })
    MERGE (c_apex)-[:WORKS_IN]->(wc_elec)
    MERGE (c_apex)-[:HAS_SPECIALIZATION]->(s_wire)
    MERGE (c_apex)-[:HAS_SPECIALIZATION]->(s_ht)
    MERGE (c_apex)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bis)
    MERGE (c_apex)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_apex)-[:AUTHORIZED_FOR {role: 'Authorized Manufacturer', territory: 'All India', valid_until: 1893456000}]->(b_hav)
    MERGE (c_apex)-[:AUTHORIZED_FOR {role: 'Authorized Vendor', territory: 'All India', valid_until: 1893456000}]->(b_poly)
    MERGE (c_apex)-[:SUPPLIES {is_oem: true, facility_name: 'Apex Cable Works', monthly_capacity: 120000}]->(p_cab)
    MERGE (c_apex)-[:ENLISTED_AS {grade: 'Class II', valid_until: 1893456000}]->(ec_elec)
    MERGE (c_apex)-[:OPERATES_IN {gstin: '29AAAAA1111A1Z5', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_apex)-[:OPERATES_IN {gstin: '27AAAAA1111A1Z8', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)

    // Past bid history establishing 5-hop lookalike path
    MERGE (c_apex)-[:BID_HISTORY {outcome: 'WON', bid_amount: 82000000.0, won_at: 1689000000}]->(t_past)
    MERGE (c_apex)-[:DEPARTMENT_AFFINITY {wins: 3, losses: 1, win_rate: 0.75, affinity_weight: 0.1875}]->(d_hurl)
    """)

    # Client 3: Kaveri Civil & Structural Infra Ltd (Civil & Earthworks)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (wc_civ:WorkCategory {name: 'Civil Works'})
    MATCH (s_civ:Specialization {name: 'Civil Contractor'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})
    MATCH (ec_civ:EnlistmentClass {code: 'CPWD-CLASS-I-CIVIL'})
    MERGE (c_cpwd:Certification {name: 'CPWD'})
    MERGE (c_is1786:Certification {name: 'IS 1786'})
    MERGE (p_pcc:Product {name: 'PCC M20 foundation and plinth'})
    MERGE (p_stl:Product {name: 'Reinforcement steel Fe500D'})

    MERGE (c_kav:Client {
        id: 'client_kaveri',
        name: 'Kaveri Civil & Structural Infra Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2012-03-10',
        legal_form: 'PRIVATE_LIMITED',
        turnover_fy24: 200000000.0,
        turnover_fy25: 220000000.0,
        turnover_fy26: 240000000.0,
        avg_turnover_3yr: 220000000.0,
        net_worth: 80000000.0,
        solvency: 90000000.0,
        ongoing_work_value: 35000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 50,
        portal_seller_id: 'KAVERI-GEM-003'
    })
    MERGE (c_kav)-[:WORKS_IN]->(wc_civ)
    MERGE (c_kav)-[:HAS_SPECIALIZATION]->(s_civ)
    MERGE (c_kav)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_kav)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_cpwd)
    MERGE (c_kav)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_is1786)
    MERGE (c_kav)-[:SUPPLIES {is_oem: false, facility_name: 'Kaveri Precast Facility', monthly_capacity: 10000}]->(p_pcc)
    MERGE (c_kav)-[:SUPPLIES {is_oem: false, facility_name: 'Kaveri Rebar Fabrication', monthly_capacity: 50000}]->(p_stl)
    MERGE (c_kav)-[:ENLISTED_AS {grade: 'Class I', valid_until: 1893456000}]->(ec_civ)
    MERGE (c_kav)-[:OPERATES_IN {gstin: '29CCCCC3333C1Z6', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_kav)-[:OPERATES_IN {gstin: '27CCCCC3333C1Z2', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    """)

    # Client 4: Lakshya Highway & Infrastructure Ltd (Heavy Civil & NHAI EPC)
    graph.query("""
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (r_as:Region {name: 'Assam'})
    MATCH (r_up:Region {name: 'Uttar Pradesh'})
    MATCH (wc_civ:WorkCategory {name: 'Civil Works'})
    MATCH (s_high:Specialization {name: 'Highway EPC'})
    MATCH (s_civ:Specialization {name: 'Civil Contractor'})
    MATCH (c_cpwd:Certification {name: 'CPWD Class 1'})
    MATCH (c_is1786:Certification {name: 'IS 1786'})
    MATCH (p_stl:Product {name: 'Reinforcement Steel Fe500D'})
    MATCH (ec_nhai:EnlistmentClass {code: 'NHAI-SUPER-CLASS'})

    MERGE (c_lakshya:Client {
        id: 'client_lakshya_civil',
        name: 'Lakshya Highway & Infrastructure Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2008-01-20',
        legal_form: 'PUBLIC_LIMITED',
        turnover_fy24: 1800000000.0,
        turnover_fy25: 1950000000.0,
        turnover_fy26: 2100000000.0,
        avg_turnover_3yr: 1950000000.0,
        net_worth: 650000000.0,
        solvency: 800000000.0,
        ongoing_work_value: 400000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 320,
        portal_seller_id: 'LAKSHYA-GEM-004'
    })
    MERGE (c_lakshya)-[:WORKS_IN]->(wc_civ)
    MERGE (c_lakshya)-[:HAS_SPECIALIZATION]->(s_high)
    MERGE (c_lakshya)-[:HAS_SPECIALIZATION]->(s_civ)
    MERGE (c_lakshya)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_cpwd)
    MERGE (c_lakshya)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_is1786)
    MERGE (c_lakshya)-[:SUPPLIES {is_oem: true, facility_name: 'Lakshya Fabrication Yard', monthly_capacity: 50000}]->(p_stl)
    MERGE (c_lakshya)-[:ENLISTED_AS {grade: 'Super Class', valid_until: 1893456000}]->(ec_nhai)
    MERGE (c_lakshya)-[:OPERATES_IN {gstin: '27LLLLL4444L1Z1', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    MERGE (c_lakshya)-[:OPERATES_IN {gstin: '18LLLLL4444L1Z3', gst_valid: true, filing_status: 'ACTIVE'}]->(r_as)
    MERGE (c_lakshya)-[:OPERATES_IN {gstin: '09LLLLL4444L1Z9', gst_valid: true, filing_status: 'ACTIVE'}]->(r_up)
    """)

    # Client 5: Zenith Railtech & Telecom Systems Ltd (Railway & Track Infrastructure)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_wb:Region {name: 'West Bengal'})
    MATCH (wc_rail:WorkCategory {name: 'Railway Track Items'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})
    MATCH (ec_rail:EnlistmentClass {code: 'RAIL-CLASS-A'})

    MERGE (c_zen:Client {
        id: 'client_zenith',
        name: 'Zenith Railtech & Telecom Systems Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2014-06-18',
        legal_form: 'PRIVATE_LIMITED',
        turnover_fy24: 170000000.0,
        turnover_fy25: 185000000.0,
        turnover_fy26: 200000000.0,
        avg_turnover_3yr: 185000000.0,
        net_worth: 65000000.0,
        solvency: 80000000.0,
        ongoing_work_value: 25000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 42,
        portal_seller_id: 'ZENITH-GEM-005'
    })
    MERGE (c_zen)-[:WORKS_IN]->(wc_rail)
    MERGE (c_zen)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_zen)-[:ENLISTED_AS {grade: 'Class A', valid_until: 1893456000}]->(ec_rail)
    MERGE (c_zen)-[:OPERATES_IN {gstin: '29DDDDD4444D1Z7', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_zen)-[:OPERATES_IN {gstin: '19DDDDD4444D1Z5', gst_valid: true, filing_status: 'ACTIVE'}]->(r_wb)
    """)

    # Client 6: Bharat Digital Networks & Systems Ltd (IT Hardware, Servers & Desktops)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_dl:Region {name: 'Delhi'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (wc_it:WorkCategory {name: 'IT Hardware'})
    MATCH (s_net:Specialization {name: 'Server Network Engineering'})
    MATCH (c_27001:Certification {name: 'ISO 27001'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})
    MATCH (b_hp:Brand {name: 'HP'})
    MATCH (b_dell:Brand {name: 'Dell'})
    MATCH (b_cisco:Brand {name: 'Cisco'})
    MATCH (p_desk:Product {name: 'Desktop Computers'})
    MATCH (p_serv:Product {name: 'Enterprise Servers'})

    MERGE (c_it:Client {
        id: 'client_bharat_it',
        name: 'Bharat Digital Networks & Systems Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2015-09-12',
        legal_form: 'PUBLIC_LIMITED',
        turnover_fy24: 500000000.0,
        turnover_fy25: 550000000.0,
        turnover_fy26: 600000000.0,
        avg_turnover_3yr: 550000000.0,
        net_worth: 200000000.0,
        solvency: 250000000.0,
        ongoing_work_value: 80000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 85,
        portal_seller_id: 'BHARAT-GEM-006'
    })
    MERGE (c_it)-[:WORKS_IN]->(wc_it)
    MERGE (c_it)-[:HAS_SPECIALIZATION]->(s_net)
    MERGE (c_it)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_27001)
    MERGE (c_it)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_it)-[:AUTHORIZED_FOR {role: 'Authorized Enterprise Partner', territory: 'All India', valid_until: 1893456000}]->(b_hp)
    MERGE (c_it)-[:AUTHORIZED_FOR {role: 'Authorized Tier 1 Partner', territory: 'All India', valid_until: 1893456000}]->(b_dell)
    MERGE (c_it)-[:AUTHORIZED_FOR {role: 'Gold Certified Partner', territory: 'All India', valid_until: 1893456000}]->(b_cisco)
    MERGE (c_it)-[:SUPPLIES {is_oem: false, facility_name: 'Bengaluru Integration Center', monthly_capacity: 5000}]->(p_desk)
    MERGE (c_it)-[:SUPPLIES {is_oem: false, facility_name: 'Bengaluru Integration Center', monthly_capacity: 500}]->(p_serv)
    MERGE (c_it)-[:OPERATES_IN {gstin: '29EEEEE5555E1Z8', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_it)-[:OPERATES_IN {gstin: '07EEEEE5555E1Z2', gst_valid: true, filing_status: 'ACTIVE'}]->(r_dl)
    MERGE (c_it)-[:OPERATES_IN {gstin: '27EEEEE5555E1Z6', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    """)

    # Client 7: Vardhan Turnkey HVAC Engineers LLP (HVAC & Air Conditioning)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (r_dl:Region {name: 'Delhi'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_hvac:Specialization {name: 'HVAC Air Conditioning'})
    MATCH (c_bee:Certification {name: 'BEE 5-Star Energy'})
    MATCH (b_volt:Brand {name: 'Voltas'})
    MATCH (b_blue:Brand {name: 'Blue Star'})
    MATCH (p_vrv:Product {name: 'VRV/VRF Air Conditioning System'})

    MERGE (c_hvac:Client {
        id: 'client_vardhan_hvac',
        name: 'Vardhan Turnkey HVAC Engineers LLP',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2017-02-14',
        legal_form: 'LLP',
        turnover_fy24: 350000000.0,
        turnover_fy25: 380000000.0,
        turnover_fy26: 410000000.0,
        avg_turnover_3yr: 380000000.0,
        net_worth: 140000000.0,
        solvency: 180000000.0,
        ongoing_work_value: 50000000.0,
        is_msme: true,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 60,
        portal_seller_id: 'VARDHAN-GEM-007'
    })
    MERGE (c_hvac)-[:WORKS_IN]->(wc_elec)
    MERGE (c_hvac)-[:HAS_SPECIALIZATION]->(s_hvac)
    MERGE (c_hvac)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bee)
    MERGE (c_hvac)-[:AUTHORIZED_FOR {role: 'Authorized Turnkey Dealer', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_volt)
    MERGE (c_hvac)-[:AUTHORIZED_FOR {role: 'Certified Commercial Installer', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_blue)
    MERGE (c_hvac)-[:SUPPLIES {is_oem: false, facility_name: 'Pune Assembly Depot', monthly_capacity: 400}]->(p_vrv)
    MERGE (c_hvac)-[:OPERATES_IN {gstin: '27FFFFF6666F1Z9', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    MERGE (c_hvac)-[:OPERATES_IN {gstin: '29FFFFF6666F1Z3', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_hvac)-[:OPERATES_IN {gstin: '07FFFFF6666F1Z7', gst_valid: true, filing_status: 'ACTIVE'}]->(r_dl)
    """)

    # Client 8: Garuda Workspaces & Modular Turnkey Ltd (Office Furniture & Storage)
    graph.query("""
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (wc_fur:WorkCategory {name: 'Furniture'})
    MATCH (s_mod:Specialization {name: 'Office Modular Furnishing'})
    MATCH (c_bif:Certification {name: 'BIFMA Level 3'})
    MATCH (b_god:Brand {name: 'Godrej Interio'})
    MATCH (b_nil:Brand {name: 'Nilkamal'})
    MATCH (p_fur:Product {name: 'Ergonomic Office Furniture'})
    MATCH (p_comp:Product {name: 'Compactor Storage System'})

    MERGE (c_god:Client {
        id: 'client_garuda_furn',
        name: 'Garuda Workspaces & Modular Turnkey Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2011-11-05',
        legal_form: 'PUBLIC_LIMITED',
        turnover_fy24: 800000000.0,
        turnover_fy25: 850000000.0,
        turnover_fy26: 900000000.0,
        avg_turnover_3yr: 850000000.0,
        net_worth: 320000000.0,
        solvency: 400000000.0,
        ongoing_work_value: 120000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 110,
        portal_seller_id: 'GARUDA-GEM-008'
    })
    MERGE (c_god)-[:WORKS_IN]->(wc_fur)
    MERGE (c_god)-[:HAS_SPECIALIZATION]->(s_mod)
    MERGE (c_god)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bif)
    MERGE (c_god)-[:AUTHORIZED_FOR {role: 'Authorized System Integrator', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_god)
    MERGE (c_god)-[:AUTHORIZED_FOR {role: 'Authorized Commercial Wholesaler', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_nil)
    MERGE (c_god)-[:SUPPLIES {is_oem: true, facility_name: 'Garuda Plant Vikhroli', monthly_capacity: 15000}]->(p_fur)
    MERGE (c_god)-[:SUPPLIES {is_oem: true, facility_name: 'Garuda Plant Vikhroli', monthly_capacity: 2500}]->(p_comp)
    MERGE (c_god)-[:OPERATES_IN {gstin: '27GGGGG7777G1Z4', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    MERGE (c_god)-[:OPERATES_IN {gstin: '29GGGGG7777G1Z1', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    """)

    # Client 9: Meditech LifeSciences & Hospital Solutions Pvt Ltd (Medical Equipment)
    graph.query("""
    MATCH (r_dl:Region {name: 'Delhi'})
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_up:Region {name: 'Uttar Pradesh'})
    MATCH (wc_med:WorkCategory {name: 'Medical Equipment'})
    MATCH (s_med:Specialization {name: 'Biomedical Waste Management'})
    MATCH (c_cdsco:Certification {name: 'CDSCO Licensed'})
    MATCH (c_iso13485:Certification {name: 'ISO 13485'})
    MATCH (b_phil:Brand {name: 'Philips Healthcare'})
    MATCH (p_bio:Product {name: 'Biomedical Waste Collection Bags'})

    MERGE (c_med:Client {
        id: 'client_meditech',
        name: 'Meditech LifeSciences & Hospital Solutions Pvt Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2018-05-22',
        legal_form: 'PRIVATE_LIMITED',
        turnover_fy24: 250000000.0,
        turnover_fy25: 280000000.0,
        turnover_fy26: 310000000.0,
        avg_turnover_3yr: 280000000.0,
        net_worth: 110000000.0,
        solvency: 140000000.0,
        ongoing_work_value: 45000000.0,
        is_msme: true,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 35,
        portal_seller_id: 'MEDITECH-GEM-009'
    })
    MERGE (c_med)-[:WORKS_IN]->(wc_med)
    MERGE (c_med)-[:HAS_SPECIALIZATION]->(s_med)
    MERGE (c_med)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_cdsco)
    MERGE (c_med)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso13485)
    MERGE (c_med)-[:AUTHORIZED_FOR {role: 'Authorized Medical Systems Partner', territory: 'All India', valid_until: 1893456000}]->(b_phil)
    MERGE (c_med)-[:SUPPLIES {is_oem: true, facility_name: 'Noida Meditech Cleanroom', monthly_capacity: 100000}]->(p_bio)
    MERGE (c_med)-[:OPERATES_IN {gstin: '07HHHHH8888H1Z5', gst_valid: true, filing_status: 'ACTIVE'}]->(r_dl)
    MERGE (c_med)-[:OPERATES_IN {gstin: '29HHHHH8888H1Z8', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_med)-[:OPERATES_IN {gstin: '09HHHHH8888H1Z3', gst_valid: true, filing_status: 'ACTIVE'}]->(r_up)
    """)

    # Client 10: Kalyani Micro Steels & Heavy Fabrication (MSME Micro Enterprise)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (wc_civ:WorkCategory {name: 'Civil Works'})
    MATCH (wc_stl:WorkCategory {name: 'Steel'})
    MATCH (s_fab:Specialization {name: 'Structural Fabrication'})
    MATCH (p_stl:Product {name: 'Structural Steel Girders'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})

    MERGE (c_msme:Client {
        id: 'client_kalyani_msme',
        name: 'Kalyani Micro Steels & Heavy Fabrication (MSME)',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2019-10-10',
        legal_form: 'PROPRIETORSHIP',
        turnover_fy24: 70000000.0,
        turnover_fy25: 75000000.0,
        turnover_fy26: 80000000.0,
        avg_turnover_3yr: 75000000.0,
        net_worth: 28000000.0,
        solvency: 35000000.0,
        ongoing_work_value: 15000000.0,
        is_msme: true,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 22,
        portal_seller_id: 'KALYANI-GEM-010'
    })
    MERGE (c_msme)-[:WORKS_IN]->(wc_civ)
    MERGE (c_msme)-[:WORKS_IN]->(wc_stl)
    MERGE (c_msme)-[:HAS_SPECIALIZATION]->(s_fab)
    MERGE (c_msme)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_msme)-[:SUPPLIES {is_oem: true, facility_name: 'Bellary Fabrication Works', monthly_capacity: 8000}]->(p_stl)
    MERGE (c_msme)-[:OPERATES_IN {gstin: '29JJJJJ9999J1Z2', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_msme)-[:OPERATES_IN {gstin: '27JJJJJ9999J1Z6', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    """)

    # Client 11: Tarun CleanTech Solar EPC Solutions Ltd (Solar EPC)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (r_mh:Region {name: 'Maharashtra'})
    MATCH (r_gj:Region {name: 'Gujarat'})
    MATCH (r_rj:Region {name: 'Rajasthan'})
    MATCH (wc_sol:WorkCategory {name: 'Solar EPC'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_sol:Specialization {name: 'Solar PV Farm Erection'})
    MATCH (s_ht:Specialization {name: 'HT Substation Erection'})
    MATCH (c_iso:Certification {name: 'ISO 9001:2015'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (b_sch:Brand {name: 'Schneider Electric'})
    MATCH (b_abb:Brand {name: 'ABB'})
    MATCH (d_hurl:Department {id: 'dept_hurl'})
    MATCH (t_past2:Tender {id: 'CPPP/HURL/ELECTRICAL/2024/02'})

    MERGE (c_tarun:Client {
        id: 'client_tarun_solar',
        name: 'Tarun CleanTech Solar EPC Solutions Ltd',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2013-04-12',
        legal_form: 'PUBLIC_LIMITED',
        turnover_fy24: 1400000000.0,
        turnover_fy25: 1450000000.0,
        turnover_fy26: 1500000000.0,
        avg_turnover_3yr: 1450000000.0,
        net_worth: 550000000.0,
        solvency: 650000000.0,
        ongoing_work_value: 300000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: false,
        tech_staff_count: 240,
        portal_seller_id: 'TARUNSOLAR-GEM-011'
    })
    MERGE (c_tarun)-[:WORKS_IN]->(wc_sol)
    MERGE (c_tarun)-[:WORKS_IN]->(wc_elec)
    MERGE (c_tarun)-[:HAS_SPECIALIZATION]->(s_sol)
    MERGE (c_tarun)-[:HAS_SPECIALIZATION]->(s_ht)
    MERGE (c_tarun)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_iso)
    MERGE (c_tarun)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bis)
    MERGE (c_tarun)-[:AUTHORIZED_FOR {role: 'Strategic EPC Partner', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_hav)
    MERGE (c_tarun)-[:AUTHORIZED_FOR {role: 'Strategic EPC Partner', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_sch)
    MERGE (c_tarun)-[:AUTHORIZED_FOR {role: 'High Voltage Transmission Partner', territory: 'All India', valid_until: 1893456000, is_demo_authorization: true}]->(b_abb)
    MERGE (c_tarun)-[:OPERATES_IN {gstin: '27TTTTT0000T1Z1', gst_valid: true, filing_status: 'ACTIVE'}]->(r_mh)
    MERGE (c_tarun)-[:OPERATES_IN {gstin: '29TTTTT0000T1Z7', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    MERGE (c_tarun)-[:OPERATES_IN {gstin: '24TTTTT0000T1Z5', gst_valid: true, filing_status: 'ACTIVE'}]->(r_gj)
    MERGE (c_tarun)-[:OPERATES_IN {gstin: '08TTTTT0000T1Z3', gst_valid: true, filing_status: 'ACTIVE'}]->(r_rj)

    // Second winning anchor establishing >= 2 distinct historical winners for dept_hurl
    MERGE (c_tarun)-[:BID_HISTORY {outcome: 'WON', bid_amount: 89000000.0, won_at: 1690000000}]->(t_past2)
    MERGE (c_tarun)-[:DEPARTMENT_AFFINITY {wins: 2, losses: 1, win_rate: 0.6667, affinity_weight: 0.125}]->(d_hurl)
    """)

    # Client 12: Defaulter Infrastructure Corp (Blacklisted Defaulter)
    graph.query("""
    MATCH (r_kar:Region {name: 'Karnataka'})
    MATCH (wc_elec:WorkCategory {name: 'Electrical'})
    MATCH (s_wire:Specialization {name: 'Wire Manufacturing Facility'})
    MATCH (c_bis:Certification {name: 'BIS IS-7098'})
    MATCH (b_hav:Brand {name: 'Havells'})
    MATCH (p_cab:Product {name: 'LT/HT Armoured Cables'})

    MERGE (c_defaulter:Client {
        id: 'client_defaulter',
        name: 'Defaulter Infrastructure Corp',
        email: 'hackathon-demo@outlook.com',
        founded_date: '2011-09-01',
        legal_form: 'PRIVATE_LIMITED',
        turnover_fy24: 140000000.0,
        turnover_fy25: 150000000.0,
        turnover_fy26: 160000000.0,
        avg_turnover_3yr: 150000000.0,
        net_worth: 50000000.0,
        solvency: 70000000.0,
        ongoing_work_value: 30000000.0,
        is_msme: false,
        is_startup: false,
        local_content_class: 'CLASS-1',
        is_blacklisted: true,
        tech_staff_count: 50,
        portal_seller_id: 'DEFAULTER-GEM-012'
    })
    MERGE (c_defaulter)-[:WORKS_IN]->(wc_elec)
    MERGE (c_defaulter)-[:HAS_SPECIALIZATION]->(s_wire)
    MERGE (c_defaulter)-[:HOLDS_CERT {valid_until: 1893456000}]->(c_bis)
    MERGE (c_defaulter)-[:AUTHORIZED_FOR {role: 'Authorized Wholesaler', territory: 'Karnataka', valid_until: 1893456000}]->(b_hav)
    MERGE (c_defaulter)-[:SUPPLIES {is_oem: true, facility_name: 'Defaulter Cable Plant', monthly_capacity: 40000}]->(p_cab)
    MERGE (c_defaulter)-[:OPERATES_IN {gstin: '29EEEEE4444E1Z9', gst_valid: true, filing_status: 'ACTIVE'}]->(r_kar)
    """)

    # Add complementary demo clients and the requirements they jointly satisfy.
    seed_jv_demo_fixture(graph)

    # Multi-State National Operating Presence for legitimate non-blacklisted contractors
    graph.query("""
    MATCH (c:Client)
    WHERE c.is_blacklisted = false
    MATCH (r:Region)
    WHERE r.name IN ['Karnataka', 'Maharashtra', 'Delhi', 'Uttar Pradesh', 'Assam', 'West Bengal', 'Tamil Nadu', 'Gujarat', 'Rajasthan', 'Himachal Pradesh', 'Madhya Pradesh', 'Uttarakhand']
    MERGE (c)-[:OPERATES_IN {gst_valid: true, filing_status: 'ACTIVE'}]->(r)
    """)


    # Seed Initial Demo JV Consortium and Dispatched Alerts
    initial_jv_tree = {
        "stage1_solo_disqualification": {
            "title": "Stage 1: Solo Bidder Disqualification Gate",
            "lead_status": "Kaveri Infra Projects cannot bid alone (Turnover ₹22.00 Cr vs ₹25.00 Cr req, and lacks specialized HT Substation & OEM cable certifications).",
            "partner_status": "Surya Power & Infra cannot bid alone (Turnover ₹9.50 Cr vs ₹25.00 Cr req, and lacks CPWD Class-I Civil enlistment).",
            "gate_passed": True,
            "detail": "Neither entity can independently satisfy 100% of CPWD/GeM statutory criteria. Proceeding to Consortium Synthesis."
        },
        "stage2_financial_aggregation": {
            "title": "Stage 2: Financial Aggregation & Solvency Gate",
            "lead_turnover_cr": 22.0,
            "partner_turnover_cr": 9.5,
            "combined_turnover_cr": 31.5,
            "required_turnover_cr": 25.0,
            "buffer_cr": 6.5,
            "combined_net_worth_cr": 14.5,
            "combined_solvency_cr": 18.2,
            "gate_passed": True,
            "detail": "Combined 3-year turnover of ₹31.50 Cr satisfies 100% of financial criteria with a +₹6.50 Cr safety buffer."
        },
        "stage3_capability_union": {
            "title": "Stage 3: Multi-Hop Capability Union Gate",
            "lead_contributions": ["Civil", "Civil Works", "Highway & Bridge EPC", "CPWD Class-1A"],
            "partner_contributions": ["Electrical", "HT Substation Erection", "Havells", "LT/HT Armoured Cables"],
            "coverage_percentage": 100.0,
            "gate_passed": True,
            "detail": "Union of Civil Infrastructure, Electrical Substations, Brand Authorizations, and OEM products covers 100% of tender specifications."
        },
        "stage4_regional_compliance": {
            "title": "Stage 4: Regional Registration & Compliance Gate",
            "region": "Maharashtra",
            "lead_gst": "Synthetic demo profile records a valid GST relationship in Maharashtra",
            "partner_gst": "Synthetic demo profile records a valid GST relationship in Maharashtra",
            "blacklisting_status": "Both synthetic client nodes have is_blacklisted=false",
            "gate_passed": True,
            "detail": "Demo graph flags pass the configured regional and blacklist gates; these values are not externally verified."
        },
        "stage5_governance_recommendation": {
            "title": "Stage 5: Consortium Governance & Lead Designation",
            "designated_lead": "Kaveri Infra Projects",
            "designated_partner": "Surya Power & Infra",
            "lead_equity_share": "60%",
            "partner_equity_share": "40%",
            "synergy_score": 0.96,
            "action": "RECOMMEND_JV_FORMATION",
            "detail": "Recommended unincorporated Joint Venture with Kaveri Infra Projects as Lead Managing Partner."
        }
    }

    graph.query("""
    MATCH (t:Tender {id: 'RW/NH-12014/ 04/2025-MAH/ZONE-IV'})
    MATCH (lead:Client {id: 'client_kaveri'})
    MATCH (partner:Client {id: 'client_surya'})
    MERGE (jv:JVConsortium {id: 'jv_client_kaveri_client_surya_RW_NH_12014_04_2025_MAH_ZONE_IV'})
    SET jv.tender_id = t.id,
        jv.tender_title = t.title,
        jv.lead_id = lead.id,
        jv.lead_name = lead.name,
        jv.partner_id = partner.id,
        jv.partner_name = partner.name,
        jv.combined_turnover = 315000000.0,
        jv.required_turnover = 250000000.0,
        jv.synergy_score = 0.96,
        jv.status = 'RECOMMENDED',
        jv.decision_tree_json = $decision_tree_json,
        jv.created_at = 1700000000,
        jv.updated_at = 1700000000
    MERGE (lead)-[:LEAD_IN_CONSORTIUM]->(jv)
    MERGE (partner)-[:PARTNER_IN_CONSORTIUM]->(jv)
    MERGE (jv)-[:FORMED_FOR_TENDER]->(t)
    MERGE (lead)-[pa:PARTNERSHIP_AFFINITY]->(partner)
      ON CREATE SET pa.proposals = 1, pa.wins = 0, pa.losses = 0, pa.affinity_score = 0.85
    """, {"decision_tree_json": json.dumps(initial_jv_tree)})

    graph.query("""
    MATCH (c:Client {id: 'client_bharat_it'})
    MERGE (t:Tender {id: 'GEM/2026/R/751080'})
    ON CREATE SET t.title = 'Supply, Installation & Maintenance of Server Infrastructure and IT Hardware',
                  t.tender_amount = 12500000.0,
                  t.expected_turnover_3yr = 6000000.0,
                  t.deadline_at = 1750000000,
                  t.source_portal = 'GeM',
                  t.status = 'ACTIVE',
                  t.listed_date = '2026-10-12'
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.match_score = 0.94,
        m.match_type = 'DIRECT',
        m.status = 'ALERTED',
        m.alert_count = 1,
        m.first_matched_at = 1700000000,
        m.last_alert_sent = 1700000000
    MERGE (ad:AgentDecision {id: 'dec_seed_bharat_it'})
    SET ad.action = 'ALERT_SENT',
        ad.match_score = 0.94,
        ad.match_type = 'DIRECT',
        ad.reasoning_trace = 'Direct Qualification: Bharat Digital Networks satisfies 100% of IT Hardware, Desktop Computer, and OEM specifications with verified state GSTIN.',
        ad.path_summary = '(:Client {id: "client_bharat_it"})-[:DIRECT_MATCH]->(:Tender {id: "GEM/2026/R/751080"})',
        ad.created_at = 1700000000
    MERGE (ad)-[:FOR_CLIENT]->(c)
    MERGE (ad)-[:EVALUATED_TENDER]->(t)
    """)

    graph.query("""
    MATCH (c:Client {id: 'client_vardhan_hvac'})
    MERGE (t:Tender {id: 'GEM/2026/R/750986'})
    ON CREATE SET t.title = 'Comprehensive Maintenance and Servicing of Central HVAC and Chiller Plants',
                  t.tender_amount = 8500000.0,
                  t.expected_turnover_3yr = 4000000.0,
                  t.deadline_at = 1750000000,
                  t.source_portal = 'GeM',
                  t.status = 'ACTIVE',
                  t.listed_date = '2026-10-12'
    MERGE (c)-[m:MATCHED_TENDER]->(t)
    SET m.match_score = 0.91,
        m.match_type = 'DIRECT',
        m.status = 'ALERTED',
        m.alert_count = 1,
        m.first_matched_at = 1700000000,
        m.last_alert_sent = 1700000000
    MERGE (ad:AgentDecision {id: 'dec_seed_vardhan'})
    SET ad.action = 'ALERT_SENT',
        ad.match_score = 0.91,
        ad.match_type = 'DIRECT',
        ad.reasoning_trace = 'Direct Qualification: Vardhan HVAC Systems satisfies 100% of AC Repair & Maintenance specifications and OEM credentials.',
        ad.path_summary = '(:Client {id: "client_vardhan_hvac"})-[:DIRECT_MATCH]->(:Tender {id: "GEM/2026/R/750986"})',
        ad.created_at = 1700000000
    MERGE (ad)-[:FOR_CLIENT]->(c)
    MERGE (ad)-[:EVALUATED_TENDER]->(t)
    """)

    graph.query("""
    MATCH (c:Client {id: 'client_apex'}), (d:Department {id: 'dept_ntpc'})
    MERGE (c)-[da:DEPARTMENT_AFFINITY]->(d)
    SET da.wins = 3, da.losses = 1, da.win_rate = 0.75, da.affinity_weight = 0.1875, da.updated_at = 1700000000
    """)

    # Normalize WorkCategory variations
    graph.query("""
    MATCH (t)-[r:IN_CATEGORY]->(wc:WorkCategory)
    WHERE wc.name IN ['Civil', 'civil']
    MERGE (c:WorkCategory {name: 'Civil Works'})
    MERGE (t)-[:IN_CATEGORY]->(c)
    DELETE r
    """)
    graph.query("""
    MATCH (c:Client)-[r:WORKS_IN]->(wc:WorkCategory)
    WHERE wc.name IN ['Civil', 'civil']
    MERGE (target:WorkCategory {name: 'Civil Works'})
    MERGE (c)-[:WORKS_IN]->(target)
    DELETE r
    """)
    graph.query("""
    MATCH (wc:WorkCategory)
    WHERE wc.name IN ['Civil', 'civil']
    DETACH DELETE wc
    """)
    graph.query("""
    MATCH (t)-[r:IN_CATEGORY]->(wc:WorkCategory {name: 'IT hardware'})
    MERGE (c:WorkCategory {name: 'IT Hardware'})
    MERGE (t)-[:IN_CATEGORY]->(c)
    DELETE r
    """)
    graph.query("""
    MATCH (wc:WorkCategory {name: 'IT hardware'})
    DETACH DELETE wc
    """)

    # Query counts for summary
    m_count = graph.query("MATCH (m:Ministry) RETURN count(m)").result_set[0][0]
    d_count = graph.query("MATCH (d:Department) RETURN count(d)").result_set[0][0]
    c_count = graph.query("MATCH (c:Client) RETURN count(c)").result_set[0][0]
    t_count = graph.query("MATCH (t:Tender) RETURN count(t)").result_set[0][0]

    return {
        "status": "success",
        "schema": schema_res,
        "ministries": m_count,
        "departments": d_count,
        "clients": c_count,
        "tenders": t_count,
    }


if __name__ == "__main__":
    if "--jv-demo-only" in sys.argv:
        # Safe additive backfill for an already initialized graph. This path
        # never clears the graph or changes learned bid history.
        demo_graph = get_graph()
        seed_jv_demo_fixture(demo_graph)
        result = {"status": "success", "message": "Synthetic JV demo fixture upserted without clearing the graph."}
    else:
        force_clear = os.environ.get("FORCE_RESET", "false").lower() == "true" or "--force" in sys.argv
        result = seed_database(clear_existing=force_clear)
    print("Seed complete:", result)
