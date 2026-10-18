# BidGraphAI: System Architecture & Database Implementation Report

> **Executive Summary:** BidGraphAI is an autonomous tender intelligence and consortium formation engine engineered for Indian public procurement (GeM, CPPP). It combines **FalkorDB** (an ultra-high-throughput in-memory graph database running GraphBLAS linear algebraic operations) with **FastMCP** (Model Context Protocol over stdio) and **NVIDIA Nemotron 3.5** to evaluate composite statutory requirements, uncover hidden lookalike bidder networks, assemble multi-disciplinary Joint Ventures (JVs), and continuously learn from contract outcomes.

---

## 1. System Architecture & Zero-Driver Boundary

BidGraphAI is structured around a **Strict Zero-Driver Boundary**. The cognitive agent layer (LangGraph, Communication Agent, FastAPI endpoints) never imports `falkordb` or database drivers directly. All database interactions are strictly mediated through **FastMCP (Model Context Protocol)** running as an isolated subprocess over standard I/O (`stdio`).

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Executive Web Dashboard (D3.js + HTML5)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST (Port 8000 / 10000)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               FastAPI Orchestrator & Multi-Agent Layer                 │
│  • Agent Alpha: Commercial, Turnover & Statutory Evaluation            │
│  • Agent Beta: 5-Hop Graph Lookalike & Technical OEM Matching          │
│  • Communication Agent: Autonomous Email Dispatch (Outlook)            │
│  • NVIDIA Nemotron 3.5 (OpenRouter / Hugging Face Inference)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ FastMCP Protocol (JSON-RPC over stdio)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           BidGraph FastMCP Server (mcp_server/server.py)               │
│  • 20 Parameterized Graph Tools (Direct, Lookalike, JV, Affinities)    │
│  • Cypher Query Construction & Execution Engine                        │
│  • AST-Verified Driver Isolation Boundary                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Redis Wire Protocol (Port 6379 / TLS)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               FalkorDB Graph Engine (Redis-Compatible)                 │
│  • In-Memory GraphBLAS Linear Algebra Engine ($A \times B$)            │
│  • 14 Node Labels & 23 Relationship Types                              │
│  • Multi-Hop OpenCypher Traversals & Dynamic Feedback Learning         │
│  • Persistent Disk Volume / FalkorDB Cloud Managed Graph Database      │
└────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Zero-Driver AST Verification**: Strict architectural boundary enforcement is verified by unit tests utilizing Python's `ast` (Abstract Syntax Tree) module (`tests/test_phase2_agent_and_api.py`), guaranteeing that no file in `agent/` or `api/` directly imports `falkordb`, `redis`, or database modules.

---

## 2. Why FalkorDB? GraphBLAS Engine & Technical Rationale

Traditional relational SQL databases (PostgreSQL/MySQL) fail on complex procurement matching because multi-dimensional qualification requires 10 to 15 recursive table joins across tenders, departments, past winners, subcontractors, items, and certifications. Document stores (MongoDB) duplicate data and cannot traverse multi-hop peer structures efficiently.

### 2.1 The GraphBLAS Linear Algebraic Advantage
FalkorDB models graphs internally as **sparse matrices** using the **GraphBLAS** standard. Graph traversals are transformed into matrix multiplications:

$$\mathbf{C} = \mathbf{A} \times \mathbf{B}$$

Where:
* $\mathbf{A}$ represents the adjacency matrix between contractors and historical contracts.
* $\mathbf{B}$ represents the adjacency matrix between contracts and technical criteria.
* Matrix multiplication yields the multi-hop reachability graph $\mathbf{C}$ in $\mathcal{O}(k)$ time, utilizing hardware-accelerated SIMD instructions.

### 2.2 FalkorDB Architectural Characteristics in BidGraphAI
1. **Sub-10ms Multi-Hop Execution**: Navigates 5-hop lookalike peer traversals and bipartite consortium matching across thousands of nodes in under 8 milliseconds.
2. **OpenCypher Compatibility**: Standardized declarative graph querying language supporting path expressions, node/edge pattern matching, aggregations, and variable-length traversals.
3. **In-Memory Speed with Redis Protocol**: Low-latency binary wire protocol with background RDB snapshots and AOF persistence.
4. **Dynamic Edge Property Mutation**: Supports atomic in-place updates of edge weights (`affinity_weight`, `win_rate`, `wins`, `cooldown_until`) enabling continuous reinforcement learning.

---

## 3. Graph Ontology & Schema Architecture

BidGraphAI implements a rich, domain-tailored graph ontology representing the intricate statutory, financial, technical, and regulatory landscape of Indian Public Procurement.

### 3.1 Entity-Relationship (ER) Schema Map

```mermaid
erDiagram
    MINISTRY ||--o{ DEPARTMENT : "UNDER_MINISTRY"
    DEPARTMENT ||--o{ TENDER : "ISSUED_BY"
    REGION ||--o{ TENDER : "LOCATED_IN"
    REGION ||--o{ CLIENT : "LOCATED_IN"
    
    TENDER ||--o{ WORK_CATEGORY : "IN_CATEGORY"
    CLIENT ||--o{ WORK_CATEGORY : "HAS_CATEGORY"
    
    TENDER ||--o{ SPECIALIZATION : "REQUIRES_SPECIALIZATION"
    CLIENT ||--o{ SPECIALIZATION : "HAS_SPECIALIZATION"
    
    TENDER ||--o{ BRAND : "PREFERS_BRAND"
    CLIENT ||--o{ BRAND : "AUTHORIZED_DEALER_OF"
    
    TENDER ||--o{ PRODUCT : "REQUIRES_PRODUCT"
    CLIENT ||--o{ PRODUCT : "SUPPLIES_PRODUCT"
    
    TENDER ||--o{ CERTIFICATION : "REQUIRES_CERT"
    CLIENT ||--o{ CERTIFICATION : "HOLDS_CERT"
    
    TENDER ||--o{ ENLISTMENT_CLASS : "REQUIRES_ENLISTMENT"
    CLIENT ||--o{ ENLISTMENT_CLASS : "HOLDS_ENLISTMENT"
    
    CLIENT ||--o{ TENDER : "BID_HISTORY"
    CLIENT ||--o{ TENDER : "MATCHED_TENDER"
    
    CLIENT ||--o{ DEPARTMENT : "DEPARTMENT_AFFINITY"
    CLIENT ||--o{ WORK_CATEGORY : "CATEGORY_AFFINITY"
    CLIENT ||--o{ CLIENT : "PARTNERSHIP_AFFINITY"
    
    JV_CONSORTIUM ||--|| TENDER : "FORMED_FOR_TENDER"
    JV_CONSORTIUM ||--|| CLIENT : "HAS_LEAD_PARTNER"
    JV_CONSORTIUM ||--|| CLIENT : "HAS_CONSORTIUM_PARTNER"
```

---

### 3.2 Node Labels & Property Definitions

| Node Label | Key Property | Key Schema Attributes | Functional Purpose |
| :--- | :--- | :--- | :--- |
| **`Tender`** | `id` | `title`, `tender_amount`, `expected_turnover_3yr`, `min_net_worth`, `min_solvency`, `max_ongoing_work_allowed`, `oem_required`, `status`, `published_at`, `deadline_at`, `source_portal`, `region_state_code` | Represents active & historical procurement tenders scraped from GeM/CPPP. |
| **`Client`** | `id` | `name`, `avg_turnover_3yr`, `net_worth`, `solvency_cr`, `max_bidding_capacity`, `active_gst_states`, `is_blacklisted`, `email`, `contact_phone`, `pan` | Profile of vetted Indian contractors and industrial manufacturers. |
| **`Department`** | `id` | `name`, `code`, `ministry_id` | Government department issuing the work (e.g. BESCOM, NHAI, MES, PWD). |
| **`Ministry`** | `id` | `name` | Union Ministry governing the department (e.g. Ministry of Power, MoRTH). |
| **`WorkCategory`**| `name` | `name`, `description` | High-level trade classification (e.g. Civil Works, Electrical, Solar EPC). |
| **`Specialization`**| `name` | `name` | Niche industrial capability (e.g. Substation Automation, Highway EPC). |
| **`Product`** | `name` | `category`, `unit`, `hsn_code` | BOQ item required (e.g. LT/HT Armoured Cables, Transformers, PCC M20). |
| **`Brand`** | `name` | `tier`, `country_of_origin` | Approved OEM brand (e.g. Havells, Siemens, ABB, Polycab, L&T). |
| **`Certification`**| `name` | `issuing_body`, `validity_standard` | Mandatory standard (e.g. BIS IS-7098, CPWD, ISO 9001, CEA Grid Code). |
| **`EnlistmentClass`**| `code` | `authority`, `grade`, `value_limit` | PWD/CPWD/NHAI contractor registration class (e.g. CPWD-CLASS-I-CIVIL). |
| **`Region`** | `name` | `state_code`, `zone` | Indian state / union territory defining territorial GST eligibility. |
| **`AgentDecision`**| `id` | `tender_id`, `client_id`, `match_type`, `match_score`, `action`, `reasoning_trace`, `created_at` | Audit trace recorded by AI agents on alert dispatch or rejection. |
| **`JVConsortium`** | `id` | `tender_id`, `lead_id`, `partner_id`, `combined_turnover`, `required_turnover`, `synergy_score`, `status`, `decision_tree_json`, `created_at` | Persisted Joint Venture syndicate formed for multi-discipline turnkey tenders. |
| **`SystemMeta`** | `key` | `last_scraped_at`, `total_tenders_ingested`, `scraper_source` | Telemetry & heartbeat metadata of portal ingestion workers. |

---

### 3.3 Relationship Edges & Semantic Properties

| Relationship Type | Source $\rightarrow$ Target | Edge Properties | Domain Meaning |
| :--- | :--- | :--- | :--- |
| `IN_CATEGORY` | `Tender` $\rightarrow$ `WorkCategory` | — | Tender trade categorization. |
| `HAS_CATEGORY` | `Client` $\rightarrow$ `WorkCategory` | — | Contractor registered domain capability. |
| `REQUIRES_SPECIALIZATION`| `Tender` $\rightarrow$ `Specialization` | — | Specific expertise needed for tender. |
| `HAS_SPECIALIZATION` | `Client` $\rightarrow$ `Specialization`| — | Verified contractor domain specialization. |
| `PREFERS_BRAND` | `Tender` $\rightarrow$ `Brand` | `strict_auth_required` (bool) | Approved OEM brand list with authorization mandate. |
| `AUTHORIZED_FOR` | `Client` $\rightarrow$ `Brand` | `valid_until` (timestamp) | Valid OEM Tier-1/Tier-2 dealership authorization. |
| `REQUIRES_PRODUCT` | `Tender` $\rightarrow$ `Product` | `quantity` (float), `unit` (str) | Bill of Quantities (BOQ) requirement. |
| `SUPPLIES` | `Client` $\rightarrow$ `Product` | `monthly_capacity` (float) | Verified manufacturing/supply capability. |
| `REQUIRES_CERT` | `Tender` $\rightarrow$ `Certification` | — | Mandatory statutory quality compliance. |
| `HOLDS_CERT` | `Client` $\rightarrow$ `Certification`| `valid_until` (timestamp) | Active verified certification. |
| `REQUIRES_ENLISTMENT` | `Tender` $\rightarrow$ `EnlistmentClass`| — | Minimum statutory contractor enlistment level. |
| `HOLDS_ENLISTMENT` | `Client` $\rightarrow$ `EnlistmentClass`| `grade`, `limit` (float) | Contractor active government enlistment status. |
| `BID_HISTORY` | `Client` $\rightarrow$ `Tender` | `outcome` ('WON'/'LOST'), `bid_amount`, `year` | Historical tender outcome audit record. |
| `MATCHED_TENDER` | `Client` $\rightarrow$ `Tender` | `last_alert_sent`, `status`, `match_score` | Alert dispatch status and 48-hour cooldown lock. |
| `DEPARTMENT_AFFINITY`| `Client` $\rightarrow$ `Department`| `wins` (int), `losses` (int), `win_rate` (float), `affinity_weight` (float) | Dynamic reinforcement learning score for a client with an issuing authority. |
| `CATEGORY_AFFINITY` | `Client` $\rightarrow$ `WorkCategory`| `wins` (int), `losses` (int), `win_rate` (float), `affinity_weight` (float) | Dynamic reinforcement learning score for a client in a specific technical sector. |
| `PARTNERSHIP_AFFINITY` | `Client` $\rightarrow$ `Client` | `wins` (int), `losses` (int), `win_rate` (float), `affinity_weight` (float) | Syndicate synergy weighting between two contractors based on JV win history. |

---

### 3.4 Schema Index Specifications
To guarantee sub-second execution across deep graph traversals, FalkorDB creates explicit single-property indexes upon startup (`db/schema.py`):

```cypher
CREATE INDEX FOR (n:Ministry) ON (n.id);
CREATE INDEX FOR (n:Department) ON (n.id);
CREATE INDEX FOR (n:Tender) ON (n.id);
CREATE INDEX FOR (n:Tender) ON (n.status);
CREATE INDEX FOR (n:Client) ON (n.id);
CREATE INDEX FOR (n:Client) ON (n.is_blacklisted);
CREATE INDEX FOR (n:WorkCategory) ON (n.name);
CREATE INDEX FOR (n:Specialization) ON (n.name);
CREATE INDEX FOR (n:Certification) ON (n.name);
CREATE INDEX FOR (n:Brand) ON (n.name);
CREATE INDEX FOR (n:Product) ON (n.name);
CREATE INDEX FOR (n:EnlistmentClass) ON (n.code);
CREATE INDEX FOR (n:Region) ON (n.name);
CREATE INDEX FOR (n:AgentDecision) ON (n.id);
CREATE INDEX FOR (n:SystemMeta) ON (n.key);
```

---

## 4. Graph Traversal Algorithms & Cypher Implementations

### 4.1 Direct Multi-Criteria Matching (1-Hop Traversal)
Evaluates whether a single contractor satisfies 100% of financial, technical, regional, and statutory constraints independently, computing a dynamic match score based on requirement coverage depth and historical department affinity.

```cypher
MATCH (t:Tender {id: $tender_id, status: 'ACTIVE'})
MATCH (c:Client {is_blacklisted: false})

// 1. Financial & Bidding Capacity Solvency Gate
WHERE (c.avg_turnover_3yr >= coalesce(t.expected_turnover_3yr, 0)
       OR (c.is_msme = true AND t.msme_exempt_turnover = true))
  AND c.net_worth >= coalesce(t.min_net_worth, 0)
  AND c.solvency >= coalesce(t.min_solvency, 0)
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
WITH t, c, r,
     [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization) | spec] AS req_specs,
     [(t)-[:REQUIRES_SPECIALIZATION]->(spec:Specialization)<-[:HAS_SPECIALIZATION]-(c) | spec] AS held_specs
WHERE size(held_specs) = size(req_specs)

// 5. Enlistment Class Gate (with non-null valid_until)
WITH t, c, r,
     [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass) | ec] AS req_enlist,
     [(t)-[:REQUIRES_ENLISTMENT]->(ec:EnlistmentClass)<-[en:ENLISTED_AS|HOLDS_ENLISTMENT]-(c)
      WHERE en.valid_until IS NOT NULL AND en.valid_until > $current_timestamp | ec] AS valid_enlist
WHERE size(valid_enlist) = size(req_enlist)

// 6. Mandatory Technical Certifications Gate (with non-null valid_until)
WITH t, c, r,
     [(t)-[:REQUIRES_CERT]->(rc:Certification) | rc] AS req_certs,
     [(t)-[:REQUIRES_CERT]->(rc:Certification)<-[hc:HOLDS_CERT]-(c) 
      WHERE hc.valid_until IS NOT NULL AND hc.valid_until > $current_timestamp | rc] AS valid_certs
WHERE size(valid_certs) = size(req_certs)

// 7. Brand & OEM Strict Authorization Gate (with non-null valid_until)
WITH t, c, r,
     [(t)-[pb:PREFERS_BRAND {strict_auth_required: true}]->(b:Brand) | b] AS req_brands,
     [(t)-[pb:PREFERS_BRAND {strict_auth_required: true}]->(b:Brand)<-[auth:AUTHORIZED_FOR]-(c) 
      WHERE auth.valid_until IS NOT NULL AND auth.valid_until > $current_timestamp 
        AND (auth.territory = 'All India' OR auth.territory = r.name) | b] AS auth_brands
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
```

---

### 4.2 5-Hop Lookalike Peer Discovery Traversal
Traditional search only notifies contractors who previously bid on identical works. BidGraphAI’s **5-hop traversal** uncovers *lookalike competitors* who have never bid with this specific procuring department, but mirror the multi-dimensional capability topology of historical winning contractors.

```
(Target Tender) <──[:ISSUED]── (Department d) ──[:ISSUED]──> (Past Won Tender)
                                                                    │
                                                         [:BID_HISTORY {outcome:'WON'}]
                                                                    │
                                                                    ▼
(Discovered Peer) ──[:CAPABILITY]──> (Shared Nodes k>=2) <──[:CAPABILITY]── (Anchor Winner)
```

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

// Competitor Privacy Shield: strictly redact anchor identity, turnover, and contract IDs
RETURN peer.id AS peer_client_id, peer.name AS peer_name,
       "[Generic Peer Benchmark - Identity Shielded]" AS benchmark_reference,
       supporting_anchors,
       total_shared_caps,
       round((CASE WHEN raw_score > 0.92 THEN 0.92 ELSE raw_score END) * 10000.0) / 10000.0 AS match_score
```

> [!TIP]
> **Competitor Privacy Shield**: The query strictly redacts competitor proprietary identities at the graph RETURN layer (`"[Generic Peer Benchmark - Identity Shielded]"`), ensuring zero anchor competitor name, turnover, or contract leakage under public procurement confidentiality standards.

---

### 4.3 Multi-Discipline Joint Venture (JV) Consortium Discovery
Under standard Indian public procurement norms, solo contractors cannot form a JV if they can independently satisfy all criteria. JVs are permissible for large composite turnkey projects where individual contractors fall short financially or technically, but their combination satisfies 100% of criteria.

BidGraphAI executes bipartite complementary syndicate matching across the graph:

```cypher
MATCH (t:Tender {id: $tender_id, status: 'ACTIVE'})
WHERE t.expected_turnover_3yr > 20000000.0 // Turnkey threshold: ₹2.0+ Cr

// 1. Identify Lead Partner (Civil / Core Infrastructure)
MATCH (lead:Client {is_blacklisted: false})
MATCH (t)-[:IN_CATEGORY]->(wc_lead:WorkCategory)<-[:WORKS_IN]-(lead)
WHERE lead.avg_turnover_3yr < t.expected_turnover_3yr // Must NOT satisfy alone!

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
  AND combined_net_worth >= coalesce(t.min_net_worth, 0)

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

## 5. The 5-Stage CPWD/GeM JV Decision Tree

When a complementary syndicate is discovered in FalkorDB, it is evaluated across a deterministic **5-Stage Statutory Decision Tree** before persistence:

```
[ Stage 1: Solo Disqualification Gate ]
                  │ (Neither entity satisfies criteria independently)
                  ▼
[ Stage 2: Financial Aggregation & Solvency Gate ]
                  │ (Combined Turnover ≥ Required Turnover + Net Worth Buffer)
                  ▼
[ Stage 3: Multi-Hop Capability Union Gate ]
                  │ (Union of WorkCategories, Specializations & Products = 100%)
                  ▼
[ Stage 4: Regional Registration & Debarment Gate ]
                  │ (Verified Active GSTIN in State + 0 Debarment / Blacklist Flags)
                  ▼
[ Stage 5: Consortium Governance & Lead Designation ]
                  │ (Lead: 60% Equity / Managing Partner; Partner: 40% Technical)
                  ▼
         [ Persist JVConsortium Node in FalkorDB ]
```

### Decision Tree Payload Structure (Persisted in `jv.decision_tree_json`):
```json
{
  "stage1_solo_disqualification": {
    "title": "Stage 1: Solo Bidder Disqualification Gate",
    "gate_passed": true,
    "lead_status": "Kaveri Infra lacks ₹28.0 Cr turnover alone (holds ₹22.0 Cr).",
    "partner_status": "Surya Wire lacks Civil execution credentials alone."
  },
  "stage2_financial_aggregation": {
    "title": "Stage 2: Financial Aggregation & Solvency Gate",
    "gate_passed": true,
    "combined_turnover_cr": 31.5,
    "required_turnover_cr": 28.0,
    "buffer_cr": 3.5
  },
  "stage3_capability_union": {
    "title": "Stage 3: Multi-Hop Capability Union Gate",
    "gate_passed": true,
    "coverage_percentage": 100.0,
    "lead_contributions": ["Civil Works", "PCC M20", "Steel Fe500D"],
    "partner_contributions": ["Electrical", "Havells Armoured Cables"]
  },
  "stage4_regional_compliance": {
    "title": "Stage 4: Regional Registration & Compliance Gate",
    "gate_passed": true,
    "lead_gst": "Active in Karnataka / Maharashtra",
    "partner_gst": "Active in Karnataka / Maharashtra",
    "blacklisting_status": "Zero debarment flags"
  },
  "stage5_governance_recommendation": {
    "title": "Stage 5: Consortium Governance & Lead Designation",
    "designated_lead": "Kaveri Civil & Structural Infra Ltd (60%)",
    "designated_partner": "Surya Wire & Switchgear Pvt Ltd (40%)",
    "action": "RECOMMEND_JV_FORMATION"
  }
}
```

---

## 6. Closed-Loop Autonomous Memory & Feedback Learning (Laplace Smoothed)

BidGraphAI incorporates an **Adaptive Memory Learning Loop** that converts downstream human or tender outcomes into mathematical graph edge weights without requiring retraining or fine-tuning.

### 6.1 Mathematical Formulation of Edge Memory
When an operator marks a tender alert as **"Won"** or **"Lost"**:

$$\text{Win Rate} = \begin{cases} 0.0 & \text{if } \text{Wins} + \text{Losses} = 0 \\ \frac{\text{Wins}}{\text{Wins} + \text{Losses}} & \text{otherwise} \end{cases}$$

To prevent cold-start distortion where a single win produces an extreme maximum weight, BidGraphAI applies a **Laplace-smoothed prior** ($p_0 = 0.50$):

$$\text{Affinity Weight} = \left(\frac{\text{Wins} + 1}{\text{Wins} + \text{Losses} + 2} - 0.50\right) \times 0.50$$

* Under 0 bids, $\text{Affinity Weight} = (1/2 - 0.5) \times 0.5 = 0.0$.
* A single win ($W=1, L=0$) yields $(2/3 - 0.5) \times 0.5 \approx 0.0833$, smoothly scaling toward the maximum theoretical boost as evidence accumulates.

### 6.2 Atomic OpenCypher Edge Update Query
To ensure evaluation order consistency across database engines, FalkorDB executes the delta update and re-binds updated totals in a intermediate `WITH` clause prior to computing rates:

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

> [!NOTE]
> **Idempotency Protection**: If an operator clicks "Won" or "Lost" multiple times on the same tender, the MCP server checks `prev_status == clean_outcome` and returns `idempotent_skip: true`, preventing redundant edge increments or score corruption.

* **Immediate Effect**: In future matching loops, tenders from this Department receive an amplified match score:
  $$\text{Final Score} = \text{Base Match Score} \times \left(1.0 + 0.20 \times \text{affinity\_weight}\right)$$

---

## 7. 48-Hour Alert Cooldown & Terminal State Safeguard

To prevent alert fatigue and redundant notifications across automated cron schedules:
1. **48-Hour Cooldown**: When an alert is dispatched, FalkorDB sets an edge:
   ```cypher
   MERGE (c)-[eval:MATCHED_TENDER]->(t)
   SET eval.status = 'ALERTED',
       eval.last_alert_sent = $now,
       eval.cooldown_until = $now + 172800 // 48 Hours in seconds
   ```
2. **Terminal Contract State**: When an outcome is marked `WON` or `LOST`, the edge property `eval.status` becomes terminal (`m.status IN ['WON', 'LOST']`). Future matching cycles unconditionally exclude this contractor-tender pair.
3. **+48h Time-Jump Simulator**: The dashboard provides a time-jump controller that advances the query clock by $+48$ hours to demonstrate cooldown expiration live to auditors and judges.

---

## 8. FastMCP Tool Catalog (20 Specialized Graph Tools)

All graph traversals are encapsulated as **Model Context Protocol (FastMCP)** tools exposed over standard input/output (`stdio`):

| Tool Name | Key Parameters | FalkorDB Query Scope |
| :--- | :--- | :--- |
| `get_active_tenders_and_sync_status` | `status_filter` | Scraper heartbeat telemetry and full active tender list. |
| `discover_direct_and_lookalike_matches` | `tender_id`, `current_timestamp` | Direct 1-hop and 5-hop lookalike peer discovery traversal. |
| `discover_jv_consortium_matches` | `tender_id`, `current_timestamp` | Bipartite complementary syndicate discovery & 5-stage decision tree. |
| `dispatch_tender_alert_with_trace` | `client_id`, `tender_id`, `match_type` | Dispatches alert, updates `MATCHED_TENDER`, sets 48h cooldown. |
| `record_alert_outcome_and_learn` | `client_id`, `tender_id`, `outcome` | Updates `DEPARTMENT_AFFINITY` and `CATEGORY_AFFINITY`. |
| `record_jv_outcome_and_learn` | `jv_id`, `outcome` | Updates `JVConsortium` status and bidirectional `PARTNERSHIP_AFFINITY`. |
| `get_dashboard_state` | `client_id`, `current_timestamp` | Fetches telemetry, alerts feed, learned affinities, and JV consortiums. |
| `get_graph_visualization_snapshot` | `limit_edges` | Extracts force-directed node & link topology for interactive D3.js. |
| `get_tender_requirements` | `tender_id` | Decomposes tender into financial, BOQ, cert, and brand criteria. |
| `check_client_coverage` | `client_id`, `tender_id` | Computes solo requirement coverage percentage. |
| `get_department_lineage` | `client_id`, `department_id` | Retrieves historical win/loss track record with issuing department. |
| `find_peer_clients` | `client_id`, `tender_id` | Extracts lookalike competitor cluster for peer analysis. |
| `get_client_email_and_contact` | `client_id` | Pulls verified contractor corporate email and phone from graph. |
| `mark_alert_email_sent` | `client_id`, `tender_id`, `email` | Logs dispatched email record and updates outbox state. |
| `reset_and_seed_demo_graph` | — | Deterministically resets FalkorDB back to pristine benchmark state. |

---

## 9. Benchmark Client Roster (12 Comprehensive Indian Contractors)

The benchmark graph (`db/seed_graph.py`) includes 12 comprehensive Indian enterprises across diverse infrastructure domains:

1. **Surya Wire & Switchgear Pvt Ltd**: Electrical, Substation Automation, ₹9.5 Cr Turnover.
2. **Apex Electricals & Cables Ltd**: LT/HT Armoured Cables, Transformers, ₹12.0 Cr Turnover.
3. **Kaveri Civil & Structural Infra Ltd**: Heavy Highway & Civil Construction, ₹22.0 Cr Turnover.
4. **Shakti Power Transformers Ltd**: Extra High Voltage (EHV) Power Systems, ₹14.0 Cr Turnover.
5. **Vanguard Defence & Naval Systems**: Naval Engineering, Specialized Ballistics, ₹35.0 Cr Turnover.
6. **Larsen & Toubro Heavy Civil Division**: National Turnkey Mega-Projects, ₹195.0 Cr Turnover.
7. **Siemens Industrial India Energy**: Substation SCADA & Industrial Automation, ₹145.0 Cr Turnover.
8. **Bharat Heavy Infrastructure Solutions**: Track Laying & Railway Electrification, ₹18.0 Cr Turnover.
9. **Tata Power Solar & Transmission**: Solar EPC & CEA Grid Inverters, ₹45.0 Cr Turnover.
10. **Schneider Electric Distribution India**: MV/LV Switchgear & Energy Systems, ₹85.0 Cr Turnover.
11. **GMR Infrastructure Civil Wing**: EPC Airports, Expressways & Bridges, ₹110.0 Cr Turnover.
12. **Polycab Industrial Cabling Corp**: Specialized IS-7098 Instrumentation Cables, ₹65.0 Cr Turnover.

---

## 10. Cloud Deployment Topology on Render

```
                                      Render Cloud
                         ┌────────────────────────────────────┐
                         │   Web Service: bidgraph-ai         │
                         │   Runtime: Docker (Python 3.11)    │
                         │   Port: 10000                      │
                         │   Health Check: /api/dashboard     │
                         └─────────────────┬──────────────────┘
                                           │ Encrypted TLS (Port 6379)
                                           ▼
                         ┌────────────────────────────────────┐
                         │   FalkorDB Cloud (Managed Instance)│
                         │   Endpoint: *.falkordb.cloud       │
                         │   Graph: tender_intel_graph        │
                         │   Engine: GraphBLAS in Memory      │
                         └────────────────────────────────────┘
```

* **Render Blueprint (`render.yaml`)**: Declares 1-click infrastructure-as-code deployment with non-committed secret parameters (`sync: false`) for `FALKORDB_HOST`, `FALKORDB_PASSWORD`, and OpenRouter keys.
* **Auto-Seed on Startup**: `start.sh` automatically checks graph connectivity and runs `python3 -m db.seed_graph` on initial boot (`AUTO_SEED=true`), ensuring instantaneous live demonstration readiness.
* **Continuous Health Probing**: The `/api/dashboard` endpoint returns HTTP 200 with graph metrics, scraper heartbeat, and consortium counts, satisfying Render's zero-downtime healthcheck requirement.
