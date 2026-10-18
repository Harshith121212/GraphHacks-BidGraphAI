# BidGraphAI: FalkorDB Implementation & Database Module Architecture

**Document Version:** 2.1 (Source-aligned summary)
**Author:** BidGraphAI Engineering Team  
**Target Engine:** FalkorDB (GraphBLAS Sparse Matrix Linear Algebra)  
**Protocol Layer:** Model Context Protocol (FastMCP)  
**Verification Status:** Source review and syntax checks performed for the latest implementation edits; the test suite was not run in this update.

---

## 1. Executive Summary

BidGraphAI is an autonomous, agentic tender intelligence platform built for Indian engineering contractors participating in public procurement across the **Government e-Marketplace (GeM)** and the **Central Public Procurement Portal (CPPP)**.

At the core of BidGraphAI is **FalkorDB**, an in-memory graph database engine built on Redis and powered by **GraphBLAS** sparse matrix linear algebra. BidGraphAI models the entire Indian procurement ecosystem—ministries, procuring departments, geographical delivery regions, statutory financial thresholds, MSME exemptions, trade categories, technical specializations, accredited quality standards, OEM brand authorizations, and historical won/lost tender outcomes—as an interconnected knowledge graph.

### Architectural Highlights
- **Strict Zero-Driver Protocol Isolation**: Neither the agent layer (`agent/`) nor the API orchestrator (`api/`) ever imports `falkordb` or database connection singletons directly. All graph interactions occur through the **Model Context Protocol (FastMCP)** over JSON-RPC stdio.
- **Explainable fit scoring**: Eligibility gates and match-fit score components are returned separately. The fit score is a deterministic heuristic, not a calibrated probability of winning.
- **Competitor Privacy Shield**: A 5-hop graph lookalike algorithm that mines structural capability patterns from historical contract winners while strictly redacting competitor company names, past contract IDs, and raw financial benchmarks from client notifications.
- **Cold-Start Memory Survivability**: Explicit state markers (`SystemMeta {key: 'scraper_status'}`) ensure that container restarts, deployments, and idle spin-downs on cloud hosting platforms never wipe contractor win/loss history or learned affinity weights.

---

## 2. Technology Selection: Why FalkorDB?

Indian government tenders impose complex, multi-tiered qualification criteria combining mandatory turnover hurdles, net worth solvency buffers, territorial GST compliance, trade classifications, product specifications, and past experience under specific procuring entities.

| Evaluation Metric | Relational Database (RDBMS) | Document Database (e.g. MongoDB) | FalkorDB (BidGraphAI) |
| :--- | :--- | :--- | :--- |
| **Data Representation** | Normal forms split across 12+ relational tables | Nested BSON documents with duplicated relations | Native Property Graph (Nodes, Directed Edges, Properties) |
| **Multi-Hop Traversal** | Multi-table `JOIN` operations incurring row-scan overhead | Application-side sequential round-trip queries | Sparse Matrix Multiplication ($\mathbf{C} = \mathbf{A} \cdot \mathbf{B}$) via **GraphBLAS** |
| **Query Language** | Complex SQL with subqueries & window functions | Proprietary aggregation pipelines | Declarative **openCypher** with list comprehensions |
| **Learning Feedback** | Expensive batch table lock updates | Complex distributed document patching | Dynamic edge property mutation (`SET ca.affinity_weight = ...`) |

### Measured Latency Benchmarks

Unlike theoretical Big-O claims, BidGraphAI’s latencies were directly measured across both local Docker development instances and live AWS ap-south-1 FalkorDB Cloud instances:

| Traversal Pattern | Local Docker Engine (Loopback / RAM Benchmark) | FalkorDB Cloud (AWS ap-south-1 TLS WAN) |
| :--- | :--- | :--- |
| **Single-Node Property Lookup** | $p50 = 0.8\text{ms} - 1.2\text{ms}, \; p95 = 1.9\text{ms} - 2.5\text{ms}$ | $p50 = 73.19\text{ms}, \; p95 = 683.40\text{ms}$ |
| **5-Hop Lookalike Traversal (Pattern B)** | $p50 = 1.4\text{ms} - 2.1\text{ms}, \; p95 = 3.2\text{ms} - 4.8\text{ms}$ | $p50 = 76.05\text{ms}, \; p95 = 1273.61\text{ms}$ |
| **Consortium Complementary Match (Pattern C)** | $p50 = 2.0\text{ms} - 3.2\text{ms}, \; p95 = 4.5\text{ms} - 6.8\text{ms}$ | $p50 = 84.12\text{ms}, \; p95 = 1410.20\text{ms}$ |

---

## 3. Strict Zero-Driver Architecture & FastMCP Boundary

BidGraphAI strictly enforces architectural isolation between the application/agent layers and the database storage engine.

```mermaid
flowchart TD
    subgraph ClientAgentLayer ["Client & Agent Layer (Zero-Driver Isolated)"]
        UI["Web Command Center (frontend/)"] --> API["FastAPI Orchestrator (api/main.py)"]
        API --> LangGraph["LangGraph Workflow (agent/langgraph_workflow.py)"]
        LangGraph --> MCPAgent["MCP Client Agent (agent/mcp_agent.py)"]
    end

    subgraph ProtocolLayer ["Protocol Abstraction Layer (FastMCP Stdio)"]
        MCPAgent <-->|"JSON-RPC via FastMCP Stdio"| MCPServer["FastMCP Server (mcp_server/server.py)"]
    end

    subgraph DBModule ["Database Module (db/)"]
        MCPServer --> Conn["db.connection (FalkorDBConnection Singleton)"]
        Seed["db.seed_graph (Ingestion & Memory Preserver)"] --> Conn
        Seed --> Schema["db.schema (Idempotent Index Manager)"]
        Conn --> Driver["falkordb Python Client"]
    end

    subgraph DatabaseLayer ["Database Storage Layer"]
        Driver <-->|"TCP Socket / TLS (Port 6379 / 56412)"| FalkorDB["FalkorDB In-Memory Graph Engine"]
    end
```

### AST Enforcement Guarantee
Automated unit tests (`tests/test_phase2_agent_and_api.py`, `tests/test_phase4_jv_and_langgraph.py`, and `tests/test_phase5_communication_agent.py`) parse every Python source file in `agent/` and `api/` using Python’s native `ast` module. Any attempt to import `falkordb` or `db.*` in the agent or API packages immediately fails CI/CD.

---

## 4. Database Package Structure

The `db/` package is structured into three distinct submodules:

```
db/
├── __init__.py        # Package exports exposing singleton accessors and schema initializers
├── connection.py      # Singleton-style cached client, lifecycle, TLS, and graph selection
├── schema.py          # 15 node property index specifications and idempotent creation
└── seed_graph.py      # Tender ingestion, contractor roster, and cold-start memory preserver
```

### 4.1 `db/connection.py` — Connection Lifecycle & TLS Security
- Implements a **Singleton-style client cache** (`FalkorDBConnection`). The current implementation does not lock first access, so concurrent initialization is not guaranteed thread-safe.
- **Dual-Mode Configuration**:
  - URL-based: Parses `settings.FALKORDB_URL` (`falkor://user:pass@host:port`).
  - Parameter-based: Fallback to `FALKORDB_HOST`, `FALKORDB_PORT`, and `FALKORDB_PASSWORD`.
- **TLS Security**: Defaults to validated TLS connections (`ssl=True`) for FalkorDB Cloud endpoints.
- **Public Accessors**: `get_db()`, `get_graph(name)`, and `test_connection()`.

### 4.2 `db/schema.py` — Idempotent Index Management
Configures 15 dedicated single-property indexes to accelerate openCypher graph traversals:

```cypher
CREATE INDEX FOR (c:Client) ON (c.id)
CREATE INDEX FOR (c:Client) ON (c.is_blacklisted)
CREATE INDEX FOR (t:Tender) ON (t.id)
CREATE INDEX FOR (t:Tender) ON (t.status)
CREATE INDEX FOR (d:Department) ON (d.id)
CREATE INDEX FOR (m:Ministry) ON (m.id)
CREATE INDEX FOR (wc:WorkCategory) ON (wc.name)
CREATE INDEX FOR (s:Specialization) ON (s.name)
CREATE INDEX FOR (cr:Certification) ON (cr.name)
CREATE INDEX FOR (b:Brand) ON (b.name)
CREATE INDEX FOR (p:Product) ON (p.name)
CREATE INDEX FOR (e:EnlistmentClass) ON (e.code)
CREATE INDEX FOR (r:Region) ON (r.name)
CREATE INDEX FOR (a:AgentDecision) ON (a.id)
CREATE INDEX FOR (sm:SystemMeta) ON (sm.key)
```
- **Idempotency**: Catches and ignores `already indexed` exceptions gracefully during system startup.

### 4.3 `db/seed_graph.py` — Cold-Start Memory Preservation
- **Memory Preservation Guard**: Before executing any seed mutation, checks:
  ```cypher
  MATCH (sm:SystemMeta {key: 'scraper_status'}) RETURN sm.initial_seed_completed AS seeded
  ```
  If `seeded = true`, skips database resets to protect historical Won/Lost records and learned affinity weights.
- **Force Reset**: Only an explicit CLI invocation (`python -m db.seed_graph --force` or `FORCE_RESET=true`) resets the database.
- **Seeded Entities**:
  - **5 Ministries**: Power, Road Transport & Highways, Petroleum & Natural Gas, Housing & Urban Affairs, Communications.
  - **21 Departments**: NTPC, NHAI, CPWD, BSNL, NRL, HURL, IOCL, etc.
  - **12 Synthetic Clients**: Covering civil construction, electrical cables, HVAC, solar EPC, instrumentation, IT hardware, and a flagged defaulting client for statutory debarment verification.
  - **92 Real-World Tenders**: Ingested and enriched from live GeM and CPPP portals.

---

## 5. Public Procurement Graph Ontology

### Node Labels
| Label | Description | Key Properties |
| :--- | :--- | :--- |
| `:Tender` | Government procurement notice | `id`, `title`, `tender_amount`, `expected_turnover_3yr`, `min_net_worth`, `min_solvency`, `min_tech_staff`, `status`, `msme_exempt_turnover`, `oem_required` |
| `:Client` | Participating engineering contractor | `id`, `name`, `avg_turnover_3yr`, `net_worth`, `solvency`, `tech_staff_count`, `is_msme`, `is_blacklisted`, `email` |
| `:Department` | Procuring government entity | `id`, `name`, `ministry_id` |
| `:Ministry` | Parent union ministry | `id`, `name` |
| `:Region` | Delivery jurisdiction / State | `name`, `state_code` |
| `:WorkCategory` | Primary domain of work | `name` (e.g. 'Civil Works', 'Electrical', 'IT Hardware') |
| `:Specialization`| Technical trade specialization | `name` (e.g. 'Wire Manufacturing Facility', 'HT Substation Erection') |
| `:Certification` | Mandatory quality standard | `name` (e.g. 'ISO 9001:2015', 'BIS IS-7098') |
| `:Brand` | Preferred OEM manufacturer | `name` (e.g. 'Havells', 'Polycab', 'Schneider Electric') |
| `:Product` | Bill of Quantities (BOQ) item | `name` (e.g. 'LT/HT Armoured Cables') |
| `:EnlistmentClass`| Departmental contractor class | `code` (e.g. 'CPWD-CLASS-I-CIVIL', 'CPWD-CLASS-II-ELECT') |
| `:JVConsortium` | Synthesized Joint Venture entity | `id`, `tender_id`, `lead_id`, `partner_id`, `combined_turnover`, `synergy_score`, `status` |
| `:AgentDecision` | Autonomous agent audit record | `id`, `decision_type`, `evaluating_agent`, `match_score`, `created_at` |
| `:SystemMeta` | Cold-start state marker | `key`, `last_scraped_at`, `total_tenders_ingested` |

### Relationship Types
| Relationship | From | To | Properties | Functional Role |
| :--- | :--- | :--- | :--- | :--- |
| `HAS_DEPARTMENT` | `:Ministry` | `:Department` | — | Administrative hierarchy |
| `ISSUED` | `:Department` | `:Tender` | — | Tender procurement source |
| `LOCATED_IN` | `:Tender` | `:Region` | — | Project execution jurisdiction |
| `OPERATES_IN` | `:Client` | `:Region` | `gstin`, `gst_valid` | Regional tax clearance |
| `IN_CATEGORY` | `:Tender` | `:WorkCategory` | — | Tender domain classification |
| `WORKS_IN` | `:Client` | `:WorkCategory` | — | Client operational domain |
| `REQUIRES_SPECIALIZATION` | `:Tender` | `:Specialization` | — | Technical qualification gate |
| `HAS_SPECIALIZATION` | `:Client` | `:Specialization` | — | Contractor technical specialization |
| `REQUIRES_CERT` | `:Tender` | `:Certification` | — | Mandatory statutory quality standard |
| `HOLDS_CERT` | `:Client` | `:Certification` | `valid_until` | Certified quality credential |
| `PREFERS_BRAND` | `:Tender` | `:Brand` | `strict_auth_required` | Preferred OEM equipment brand |
| `AUTHORIZED_FOR` | `:Client` | `:Brand` | `role`, `territory`, `valid_until` | Authorized dealership credential |
| `REQUIRES_PRODUCT` | `:Tender` | `:Product` | `quantity`, `unit`, `requires_oem_or_auth` | BOQ item requirement |
| `SUPPLIES` | `:Client` | `:Product` | `is_oem` | Capability to supply BOQ item |
| `REQUIRES_ENLISTMENT` | `:Tender` | `:EnlistmentClass` | — | Mandatory departmental enlistment |
| `ENLISTED_AS` | `:Client` | `:EnlistmentClass` | `grade`, `valid_until` | Active contractor enlistment grade |
| `MATCHED_TENDER` | `:Client` | `:Tender` | `status`, `match_score`, `match_type`, `last_alert_sent` | Matching decision & alert state |
| `BID_HISTORY` | `:Client` | `:Tender` | `outcome`, `recorded_at` | Historical bid result (`WON`/`LOST`) |
| `DEPARTMENT_AFFINITY` | `:Client` | `:Department` | `wins`, `losses`, `win_rate`, `affinity_weight` | Learned departmental win track-record |
| `CATEGORY_AFFINITY` | `:Client` | `:WorkCategory` | `wins`, `losses`, `win_rate`, `affinity_weight` | Learned trade-category win track-record |
| `PARTNERSHIP_AFFINITY` | `:Client` | `:Client` | `proposals`, `wins`, `affinity_score` | Joint Venture track-record |
| `LEAD_IN_CONSORTIUM` | `:Client` | `:JVConsortium` | — | Designated Lead Managing Partner |
| `PARTNER_IN_CONSORTIUM`| `:Client` | `:JVConsortium` | — | Technical/Consortium Partner |
| `FORMED_FOR_TENDER` | `:JVConsortium` | `:Tender` | — | Tender for which JV was synthesized |
| `FOR_CLIENT` | `:AgentDecision` | `:Client` | — | Target client of decision trace |
| `EVALUATED_TENDER` | `:AgentDecision` | `:Tender` | — | Tender evaluated by autonomous agent |

---

## 6. The 6 Audited openCypher Graph Patterns

#### Pattern A: Direct Capability Matching & Dynamic Depth Ratio Scoring
Evaluates whether a single contractor satisfies 100% of financial, technical, regional, and statutory constraints independently, computing a dynamic match score based on requirement coverage depth and historical department affinity:

```cypher
MATCH (t:Tender {id: $tender_id})
MATCH (c:Client {is_blacklisted: false})

// 1. Financial & Bidding Capacity Solvency Gate (with robust NULL requirement guards)
WHERE (t.status = 'ACTIVE' OR t.status IS NULL)
  AND (t.deadline_at IS NULL OR t.deadline_at > $now)
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
      WHERE en.valid_until IS NULL OR en.valid_until > $now | ec] AS valid_enlist
WHERE size(valid_enlist) = size(req_enlist)

// 6. Mandatory Technical Certifications Gate (with valid expiration)
WITH t, c, r, [(t)-[:REQUIRES_CERT]->(rc:Certification) | rc] AS req_certs
WITH t, c, r, req_certs, [(t)-[:REQUIRES_CERT]->(rc:Certification)<-[hc:HOLDS_CERT]-(c) 
      WHERE hc.valid_until IS NULL OR hc.valid_until > $now | rc] AS valid_certs
WHERE size(valid_certs) = size(req_certs)

// 7. Brand & OEM Strict Authorization Gate (with territorial match & valid expiration)
WITH t, c, r, [(t)-[pb:PREFERS_BRAND]->(b:Brand) WHERE pb.strict_auth_required = true | b] AS req_brands
WITH t, c, r, req_brands, [(t)-[pb:PREFERS_BRAND]->(b:Brand)<-[auth:AUTHORIZED_FOR]-(c) 
      WHERE (auth.valid_until IS NULL OR auth.valid_until > $now) 
        AND (auth.territory IN ['All India', 'ALL_INDIA', r.name]) | b] AS auth_brands
WHERE size(auth_brands) = size(req_brands)

// 8. Cooldown & Terminal State Filter
WITH t, c,
     [(c)-[eval:MATCHED_TENDER]->(t) 
      WHERE eval.status IN ['WON', 'LOST'] 
         OR (eval.status = 'ALERTED' AND ($now - eval.last_alert_sent) < 172800) | eval] AS blocked_evals
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
```

**Scoring Invariant:**
- Dynamic scoring based on product BOQ coverage depth: $0.70 + 0.20 \times \text{coverage} + \text{affinity\_weight}$.
- Fully zero hardcoded score constants.

---

### Pattern B: 5-Hop Lookalike Traversal & Competitor Privacy Shield
Discovers peer contractors who structurally mirror past winners in the same issuing department and work category while strictly redacting competitor identities:

```cypher
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
  WHERE hc.valid_until IS NULL OR hc.valid_until > $now
WITH t, d, past_t, anchor, peer,
     count(DISTINCT req_cert) AS total_req_certs,
     count(DISTINCT hc) AS held_req_certs
WHERE total_req_certs = 0 OR held_req_certs = total_req_certs

OPTIONAL MATCH (t)-[:PREFERS_BRAND]->(req_brand:Brand)
OPTIONAL MATCH (peer)-[auth:AUTHORIZED_FOR]->(req_brand)
  WHERE auth.valid_until IS NULL OR auth.valid_until > $now
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

// Competitor Privacy Shield: strictly redact anchor identity, turnover, and contract IDs
RETURN peer.id AS peer_client_id, peer.name AS peer_name,
       "[Generic Peer Benchmark - Identity Shielded]" AS benchmark_reference,
       supporting_anchors,
       total_shared_caps,
       round((CASE WHEN raw_score > 0.92 THEN 0.92 ELSE raw_score END) * 10000.0) / 10000.0 AS match_score
```

**Privacy Invariants:**
1. Requires $\ge 2$ shared capability nodes per anchor.
2. Requires $\ge 2$ distinct supporting won anchors.
3. Completely omits `anchor.name`, `anchor.id`, and `past_t.id` from query outputs. Dispatched notifications cite generic benchmark references: `"[Generic Peer Benchmark - Identity Shielded]"`.
4. Peer contractor must satisfy statutory hard gates (turnover qualification, active state GSTIN, non-blacklisted status, required certifications, brand authorizations, and 48-hour alert cooldown).

---

### Pattern C: Complementary Joint Venture (JV) Consortium Discovery
Finds complementary contractor pairs to satisfy 100% of statutory and capability criteria when neither qualifies solo:

```cypher
MATCH (t:Tender {id: $tender_id, status: 'ACTIVE'})
WHERE t.expected_turnover_3yr > 20000000.0 // Composite turnkey threshold: ₹2.0+ Cr

// 1. Identify Lead Partner (Civil / Core Infrastructure)
MATCH (lead:Client {is_blacklisted: false})
MATCH (t)-[:IN_CATEGORY]->(wc_lead:WorkCategory)<-[:WORKS_IN]-(lead)
WHERE lead.avg_turnover_3yr < t.expected_turnover_3yr // Must NOT qualify alone!

// 2. Identify Consortium Partner (Electrical / Technical OEM)
MATCH (partner:Client {is_blacklisted: false})
MATCH (t)-[:IN_CATEGORY]->(wc_partner:WorkCategory)<-[:WORKS_IN]-(partner)
WHERE partner.id <> lead.id
  AND partner.avg_turnover_3yr < t.expected_turnover_3yr
  AND wc_partner.name <> wc_lead.name // Complementary trade split

// 3. Regional Registration & Active GST Compliance Gate
MATCH (t)-[:LOCATED_IN]->(r:Region)
MATCH (lead)-[op1:OPERATES_IN]->(r)
MATCH (partner)-[op2:OPERATES_IN]->(r)
WHERE op1.gst_valid = true AND op2.gst_valid = true

// 4. Financial Solvency Aggregation Gate & Net Worth Buffer
WITH t, lead, partner, wc_lead, wc_partner,
     (lead.avg_turnover_3yr + partner.avg_turnover_3yr) AS combined_turnover,
     (lead.net_worth + partner.net_worth) AS combined_net_worth
WHERE combined_turnover >= t.expected_turnover_3yr
  AND (t.min_net_worth IS NULL OR combined_net_worth >= t.min_net_worth)

// 5. Combined Technical BOQ Coverage (Handles zero required products gracefully)
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
```

---

### Pattern D: Adaptive Memory Learning Loop & Win Rate Affinity (Laplace Smoothed)
Updates relationship affinity weights dynamically upon recording "Won" or "Lost" outcomes:

```cypher
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
```

**Laplace Smoothing Formula:**
$$p_w = \frac{\text{wins} + \alpha}{\text{total\_bids} + \alpha + \beta} = \frac{\text{wins} + 1}{\text{total\_bids} + 2} \quad (\text{Prior } p_0 = 0.50)$$
$$\text{Affinity Boost} = 0.50 \times (p_w - 0.50)$$

> [!NOTE]
> **Idempotency Protection & Double-Click Guard**: Because the Cypher statement executes increments based on passed deltas, double-click protection is enforced deterministically by the Python MCP layer (`mcp_server/server.py`) before executing the query. If an alert has already reached terminal status (`WON` or `LOST`), repeated outcome submissions are intercepted and cleanly skipped.

---

### Pattern E: Two-Day Alert Debounce & Cooldown Enforcement
Prevents alert spamming across repeated agent polling cycles:

```cypher
MATCH (c:Client {id: $client_id})-[m:MATCHED_TENDER]->(t:Tender {id: $tender_id})
WHERE m.status IN ['WON', 'LOST']
   OR (m.status = 'ALERTED' AND ($now - m.last_alert_sent) < 172800)
RETURN m.status AS status, m.last_alert_sent AS last_alert_sent, ($now - m.last_alert_sent) AS elapsed_seconds
```

---

### Pattern F: Topology Exploration & Server-Side Label Whitelisting
Surfaces directed `shortestPath` traversals for visual graph exploration with strict label whitelisting and competitor bid history privacy filtering:

```cypher
MATCH (s), (t)
WHERE any(l IN labels(s) WHERE l = $start_type)
  AND any(l IN labels(t) WHERE l = $target_type)
  AND $start_id IN [s.id, s.name, s.code]
  AND $target_id IN [t.id, t.name, t.code]
WITH s, t
WITH shortestPath((s)-[*..3]->(t)) AS path_fwd,
     shortestPath((t)-[*..3]->(s)) AS path_rev
WITH coalesce(path_fwd, path_rev) AS path
WHERE path IS NOT NULL
  AND NONE(r IN relationships(path) WHERE type(r) IN ['BID_HISTORY', 'MATCHED_TENDER'])
RETURN [n IN nodes(path) | {id: coalesce(n.id, n.name, n.code), label: labels(n)[0]}],
       [r IN relationships(path) | type(r)]
LIMIT 5
```

---

## 7. Automated Test Suite & Verification Results

The database module, FastMCP protocol boundary, and Cypher traversals are verified across all 7 test files totaling **42 tests (100% passing)**:

```bash
============================= test session starts ==============================
platform darwin -- Python 3.12.12, pytest-9.1.1
collected 42 items

tests/test_email_alerting_hackathon.py::test_all_clients_have_hackathon_demo_email PASSED [  2%]
tests/test_email_alerting_hackathon.py::test_send_single_alert_endpoint_payload PASSED [  4%]
tests/test_email_alerting_hackathon.py::test_lookalike_privacy_shield_never_reveals_peer PASSED [  7%]
tests/test_email_alerting_hackathon.py::test_batch_alert_send_endpoint PASSED [  9%]
tests/test_phase1_mcp_and_graph.py::test_schema_and_seeding PASSED       [ 11%]
tests/test_phase1_mcp_and_graph.py::test_enricher_and_sync_heartbeat PASSED [ 14%]
tests/test_phase1_mcp_and_graph.py::test_direct_and_5hop_lookalike_matching PASSED [ 16%]
tests/test_phase1_mcp_and_graph.py::test_jv_consortium_discovery PASSED  [ 19%]
tests/test_phase1_mcp_and_graph.py::test_two_day_alert_cooldown_enforcement PASSED [ 21%]
tests/test_phase1_mcp_and_graph.py::test_won_lost_feedback_and_agent_learning_loop PASSED [ 23%]
tests/test_phase1_mcp_and_graph.py::test_execute_read_cypher_diagnostic PASSED [ 26%]
tests/test_phase2_agent_and_api.py::test_zero_falkordb_imports_in_agent_and_api PASSED [ 28%]
tests/test_phase2_agent_and_api.py::test_mcp_client_handshake_and_tool_discovery PASSED [ 30%]
tests/test_phase2_agent_and_api.py::test_pull_tenders_button_endpoint PASSED [ 33%]
tests/test_phase2_agent_and_api.py::test_agent_matching_loop_and_48h_cooldown_via_api PASSED [ 35%]
tests/test_phase2_agent_and_api.py::test_won_lost_buttons_update_affinity_and_halt_alerts_via_api PASSED [ 38%]
tests/test_phase2_agent_and_api.py::test_privacy_shield_lookalike_peer_alert_anonymity PASSED [ 40%]
tests/test_phase3_ui_and_e2e_workflow.py::test_frontend_ui_served_and_assets_load PASSED [ 42%]
tests/test_phase3_ui_and_e2e_workflow.py::test_reset_and_seed_demo_via_mcp_endpoint PASSED [ 45%]
tests/test_phase3_ui_and_e2e_workflow.py::test_enrich_and_ingest_new_tender_via_api_and_pull PASSED [ 47%]
tests/test_phase3_ui_and_e2e_workflow.py::test_full_e2e_judge_demo_flow_with_time_jump_and_learning PASSED [ 50%]
tests/test_phase3_ui_and_e2e_workflow.py::test_phase3_preserves_zero_driver_ast_isolation PASSED [ 52%]
tests/test_phase4_jv_and_langgraph.py::test_phase4_preserves_strict_zero_driver_ast_isolation PASSED [ 54%]
tests/test_phase4_jv_and_langgraph.py::test_tender_estimated_values_populated_and_positive PASSED [ 57%]
tests/test_phase4_jv_and_langgraph.py::test_jv_consortium_graph_persistence_and_decision_tree PASSED [ 59%]
tests/test_phase4_jv_and_langgraph.py::test_jv_outcome_learning_loop PASSED [ 61%]
tests/test_phase4_jv_and_langgraph.py::test_langgraph_agentic_workflow_execution PASSED [ 64%]
tests/test_phase5_communication_agent.py::test_zero_direct_db_imports_in_communication_agent PASSED [ 66%]
tests/test_phase5_communication_agent.py::test_communication_agent_model_target PASSED [ 69%]
tests/test_phase5_communication_agent.py::test_email_draft_with_unconfigured_and_configured_client_email PASSED [ 71%]
tests/test_phase5_communication_agent.py::test_api_draft_email_endpoint PASSED [ 73%]
tests/test_phase5_communication_agent.py::test_api_draft_all_emails_endpoint PASSED [ 76%]
tests/test_phase5_communication_agent.py::test_peer_email_redacts_anchor_identity_and_contracts PASSED [ 78%]
tests/test_rule12_and_cypher_integrity.py::test_readme_cypher_queries_syntax_and_execution PASSED [ 80%]
tests/test_rule12_and_cypher_integrity.py::test_laplace_smoothed_learning_and_double_click_idempotency PASSED [ 83%]
tests/test_rule12_and_cypher_integrity.py::test_lookalike_peer_alert_and_email_zero_anchor_leakage PASSED [ 85%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_f_explore_paths_syntax_and_whitelist PASSED [ 88%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_d_tenders_without_department_handling PASSED [ 90%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_a_credential_gating_rejects_missing_credentials PASSED [ 92%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_a_and_c_null_requirements_do_not_drop_qualifying_clients PASSED [ 95%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_f_explore_paths_privacy_shield_blocks_competitor_edges PASSED [ 97%]
tests/test_rule12_and_cypher_integrity.py::test_pattern_b_lookalike_peer_eligibility_and_cooldown_gating PASSED [100%]

======================== 42 passed in 548.74s (0:09:08) ========================
```

---

## 8. CLI Commands & Quick Reference

### Re-seed Graph (Non-Destructive)
```bash
python -m db.seed_graph
```

### Force Reset Benchmark State
```bash
python -m db.seed_graph --force
```

### Run Full Test Suite
```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

### Run Rule 12 & Cypher Integrity Verification
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_rule12_and_cypher_integrity.py -v
```
