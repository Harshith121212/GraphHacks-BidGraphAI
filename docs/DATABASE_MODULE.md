# BidGraphAI Database Module Architecture & FalkorDB Implementation Guide

This document provides a comprehensive, deep-dive reference for the `db/` module and the complete **FalkorDB** implementation in **BidGraphAI**. It details the underlying graph database technology, connection lifecycle, zero-driver protocol isolation, idempotent schema indexing, multi-hop procurement ontology, cold-start memory preservation mechanics, and audited Cypher execution patterns.

---

## 1. Architectural Role & Database Selection

### 1.1 Why FalkorDB?
BidGraphAI operates on deeply interconnected Indian public procurement data from the **Government e-Marketplace (GeM)** and the **Central Public Procurement Portal (CPPP)**. 

Evaluating contractor eligibility across financial limits, territorial GST registrations, trade classifications, technical certifications, OEM brand authorizations, and historical win rates requires traversing multi-hop relationship paths. In traditional relational databases (RDBMS), multi-table `JOIN` operations incur significant row-scan overhead as relationship depth increases. Document stores (MongoDB, DynamoDB) fail to express bidirectional topological relationship graphs efficiently, requiring multiple sequential round-trip lookups.

BidGraphAI utilizes **FalkorDB**, an in-memory graph database engine built on **GraphBLAS** sparse matrix linear algebra:
1. **Sparse Matrix Linear Algebra (GraphBLAS)**: Evaluating a 5-hop traversal path (`Client -> Specialization -> Tender -> Department -> Past Tender -> Winner`) maps graph traversals into sparse matrix multiplications ($\mathbf{C} = \mathbf{A} \cdot \mathbf{B}$).
   - **Local Docker Engine (loopback / Unix socket benchmark)**:
     - Single-node property lookup: $p50 = 0.8\text{ms} - 1.2\text{ms}$, $p95 = 1.9\text{ms} - 2.5\text{ms}$.
     - Multi-hop traversal (5 hops): $p50 = 1.4\text{ms} - 2.1\text{ms}$, $p95 = 3.2\text{ms} - 4.8\text{ms}$.
   - **FalkorDB Cloud Instance (AWS ap-south-1 over WAN TLS)**:
     - Measured Single Node Lookup: $p50 = 73.19\text{ms}$, $p95 = 683.40\text{ms}$.
     - Measured Multi-Hop 5-Hop Traversal: $p50 = 76.05\text{ms}$, $p95 = 1273.61\text{ms}$.
     *(Includes geographic WAN latency, TLS cryptographic handshake, and server evaluation).*
2. **OpenCypher Compatibility**: FalkorDB supports standard declarative openCypher syntax, enabling complex list comprehensions, dynamic aggregations, and graph pattern matching.
3. **Session & Cold-Start Survivability**: Rather than relying on cloud free-tier snapshot persistence (which may spin down on idle), BidGraphAI embeds explicit state markers (`SystemMeta {key: 'scraper_status'}`). Startup scripts (`start.sh` and `seed_graph.py`) seed fresh data only if metadata is missing, ensuring Won/Lost outcome memory and learned affinity weights survive container cold-starts.

---

### 1.2 Strict Zero-Driver Architecture & FastMCP Protocol Boundary

A core architectural invariant of BidGraphAI is that **neither the agent layer (`agent/`) nor the API orchestrator (`api/`) ever imports `falkordb` or database connection singletons directly**.

All graph operations execute through the **Model Context Protocol (FastMCP)** layer via standardized stdio JSON-RPC tools (`mcp_server/server.py`):

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

> [!IMPORTANT]
> **Automated AST Enforcement**: Zero-driver isolation is continuously enforced by automated Abstract Syntax Tree (AST) unit tests (`tests/test_phase3_ui_and_e2e_workflow.py` and `tests/test_phase5_communication_agent.py`). Any direct import of `falkordb` or `db.*` in the agent or API layer fails CI/CD immediately.

---

## 2. Component Breakdown of the `db/` Package

The `db/` package is structured into three specialized submodules:

```
db/
├── __init__.py        # Package exports exposing singleton accessors and schema initializers
├── connection.py      # Thread-safe Singleton managing client lifecycle, TLS, and pooling
├── schema.py          # 15 node property index specifications and idempotent creation
└── seed_graph.py      # Tender ingestion, contractor roster, and cold-start memory preserver
```

---

### 2.1 `db/connection.py` — Singleton Connection Manager

[`db/connection.py`](../db/connection.py) implements a thread-safe **Singleton** pattern ensuring that only a single FalkorDB client instance exists per Python process. It transparently supports both local Docker environments and encrypted FalkorDB Cloud instances.

#### Key Implementation Details:

1. **Thread-Safe Singleton Pattern**:
   ```python
   class FalkorDBConnection:
       _instance: Optional["FalkorDBConnection"] = None
       _client: Optional[FalkorDB] = None

       def __new__(cls) -> "FalkorDBConnection":
           if cls._instance is None:
               cls._instance = super(FalkorDBConnection, cls).__new__(cls)
           return cls._instance
   ```

2. **Dual-Mode Connection Resolution**:
   - **URL-Based**: When `settings.FALKORDB_URL` is configured (e.g., `falkor://user:pass@host:port`), `FalkorDB.from_url()` is used directly.
   - **Parameter-Based**: When individual environment variables are supplied (`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`, `FALKORDB_SSL`), connection arguments are constructed dynamically.

3. **Cloud TLS Configuration & Verification-First Security**:
   All communication over the public internet to FalkorDB Cloud uses TLS encryption (`ssl=True`). BidGraphAI adopts a **Verification-First** architecture (`FALKORDB_SSL_VERIFY = True` by default):
   - Strict SSL certificate and hostname verification is attempted first during socket handshake.
   - If certificate validation fails due to cloud provider dynamic multi-tenant subdomains (e.g., AWS wildcard mismatch), the driver automatically falls back to TLS encrypted transport without hostname checking, logging an explicit security notice (see detailed analysis in [SECURITY.md](SECURITY.md)):
   ```python
   if settings.FALKORDB_SSL:
       connection_kwargs["ssl"] = True
       if settings.FALKORDB_SSL_VERIFY:
           connection_kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
           connection_kwargs["ssl_check_hostname"] = True
   ```

4. **Target Graph Selection**:
   The `get_graph(graph_name: Optional[str] = None)` method selects the active working graph, defaulting to `settings.FALKORDB_GRAPH_NAME` (typically `tender_intel_graph`).

5. **Safe Connection Diagnostics (`test_connection()`)**:
   Provides an automated latency and availability check with masked host credentials for safe diagnostic logging:
   ```python
   {
       "status": "connected",
       "host": "r-6jis***9fe2baddeda5",
       "port": 56412,
       "ssl": True,
       "latency_ms": 14.2,
       "graphs": ["tender_intel_graph"]
   }
   ```

---

### 2.2 `db/schema.py` — Idempotent Index Manager

[`db/schema.py`](../db/schema.py) establishes indexing across high-cardinality node labels and lookup properties.

#### Complete Index Specifications (`INDEX_SPECIFICATIONS`):

| Node Label | Indexed Property | Traversal & Filtering Optimization |
| :--- | :--- | :--- |
| `Ministry` | `id` | Departmental hierarchy resolution |
| `Department` | `id` | Procuring entity resolution and affinity lookups |
| `Tender` | `id` | Primary key lookup for ingestion, matching, and alert dispatch |
| `Tender` | `status` | Rapid filtering of `ACTIVE` tenders vs historical contracts |
| `Client` | `id` | Direct contractor identity resolution |
| `Client` | `is_blacklisted` | Statutory debarment exclusion gate |
| `WorkCategory` | `name` | Core trade category alignment (Civil, Electrical, IT, etc.) |
| `Specialization` | `name` | Specialized operational capability matching |
| `Certification` | `name` | Mandatory compliance verification (BIS, ISO, NABL, etc.) |
| `Brand` | `name` | OEM preferred vendor and authorized dealer matching |
| `Product` | `name` | Bill of Quantities (BOQ) line-item matching |
| `EnlistmentClass` | `code` | CPWD, NHAI, and Railway contractor grade eligibility |
| `Region` | `name` | Territorial jurisdiction and GST compliance gates |
| `AgentDecision` | `id` | Autonomous decision trace auditing and deduplication |
| `SystemMeta` | `key` | System heartbeat and cold-start memory marker |

#### Idempotency Guard:
Executing `CREATE INDEX` multiple times in FalkorDB raises an exception if the index already exists. [`initialize_schema()`](../db/schema.py) inspects the error message for `"already indexed"` or `"index already exists"`, converting would-be crashes into clean operational skips:

```python
try:
    graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    created.append(f"{label}.{prop}")
except Exception as exc:
    if "already indexed" in str(exc).lower() or "already exists" in str(exc).lower():
        existing.append(f"{label}.{prop}")
    else:
        errors.append(f"{label}.{prop}: {exc}")
```

---

### 2.3 `db/seed_graph.py` — Seeder & Cold-Start Memory Preserver

[`db/seed_graph.py`](../db/seed_graph.py) constructs the complete multi-hop Indian procurement environment, parsing raw tender data and wiring domain relationships.

#### Cold-Start Memory Preservation Mechanics
On cloud platforms with ephemeral or auto-idling containers (such as Render's Free Web Service tier), instances spin down after 15 minutes of inactivity. When a new incoming HTTP request wakes the instance:
1. `start.sh` executes on container boot.
2. In naive setups, running `seed_database()` on boot would clear the graph via `graph.delete()`, instantly wiping all historical won/lost outcomes, learned affinity weights, and cooldown timestamps.
3. BidGraphAI enforces **Memory Survival**:
   ```python
   # Memory Survival Check: if not explicitly forcing a clear, check for existing SystemMeta marker
   if not clear_existing:
       try:
           check_res = graph.query("MATCH (sm:SystemMeta {key: 'scraper_status'}) RETURN sm.total_tenders_ingested").result_set
           if check_res and len(check_res) > 0:
               logger.info("SystemMeta marker found in FalkorDB; graph already initialized. Preserving memory across cold start.")
               return {
                   "status": "preserved",
                   "message": "Graph already initialized. Persistent Won/Lost memory and affinity weights preserved.",
                   "total_tenders": check_res[0][0] if check_res[0] else 26,
               }
       except Exception as exc:
           logger.debug("Could not verify existing SystemMeta marker: %s", exc)
   ```
4. Destructive resets require an explicit administrative action (`FORCE_RESET=true` or `--force`).

---

## 3. Complete Graph Ontology & Entity-Relationship Model

The graph models the complex statutory, technical, and commercial relationships of Indian public procurement.

```mermaid
classDiagram
    class Ministry {
        string id PK
        string name
    }
    class Department {
        string id PK
        string ministry_id
        string name
    }
    class Tender {
        string id PK
        string title
        string reference_no
        float tender_amount
        float expected_turnover_3yr
        float min_net_worth
        float min_solvency
        float max_ongoing_work_allowed
        boolean oem_required
        string min_local_content_class
        int min_tech_staff
        boolean msme_exempt_turnover
        string status
        int published_at
        int deadline_at
        string source_portal
    }
    class Client {
        string id PK
        string name
        string email
        string founded_date
        string legal_form
        float avg_turnover_3yr
        float net_worth
        float solvency
        float ongoing_work_value
        boolean is_msme
        boolean is_startup
        string local_content_class
        boolean is_blacklisted
        int tech_staff_count
        string portal_seller_id
    }
    class WorkCategory {
        string name PK
    }
    class Specialization {
        string name PK
    }
    class Certification {
        string name PK
    }
    class Brand {
        string name PK
        boolean is_demo_sample
    }
    class Product {
        string name PK
        string category
    }
    class EnlistmentClass {
        string code PK
        string authority
        string grade
        float value_limit
    }
    class Region {
        string name PK
        string state_code
    }
    class JVConsortium {
        string id PK
        string tender_id
        string lead_id
        string partner_id
        float combined_turnover
        float synergy_score
        string decision_tree_json
    }
    class AgentDecision {
        string id PK
        string action
        float match_score
        string match_type
        string reasoning_trace
        string path_summary
        int created_at
    }

    Ministry "1" --> "*" Department : HAS_DEPARTMENT
    Department "1" --> "*" Tender : ISSUED
    Tender --> Region : LOCATED_IN
    Tender --> WorkCategory : IN_CATEGORY
    Tender --> Specialization : REQUIRES_SPECIALIZATION
    Tender --> Certification : REQUIRES_CERT
    Tender --> Brand : PREFERS_BRAND
    Tender --> Product : REQUIRES_PRODUCT
    Tender --> EnlistmentClass : REQUIRES_ENLISTMENT

    Client --> WorkCategory : WORKS_IN
    Client --> Specialization : HAS_SPECIALIZATION
    Client --> Certification : HOLDS_CERT
    Client --> Brand : AUTHORIZED_FOR
    Client --> Product : SUPPLIES
    Client --> EnlistmentClass : HOLDS_ENLISTMENT
    Client --> Region : OPERATES_IN

    Client --> Tender : MATCHED_TENDER
    Client --> Tender : BID_HISTORY
    Client --> Department : DEPARTMENT_AFFINITY
    Client --> Client : PARTNERSHIP_AFFINITY

    Client --> JVConsortium : LEAD_IN_CONSORTIUM
    Client --> JVConsortium : PARTNER_IN_CONSORTIUM
    JVConsortium --> Tender : FORMED_FOR_TENDER

    AgentDecision --> Client : FOR_CLIENT
    AgentDecision --> Tender : EVALUATED_TENDER
```

---

### 3.1 Node Label Taxonomy

| Node Label | Key Property | Sample Instance | Description |
| :--- | :--- | :--- | :--- |
| `Ministry` | `id` | `min_power` | Union Cabinet Ministry (e.g., Ministry of Power, MoRTH). |
| `Department` | `id` | `dept_hurl`, `dept_ntpc` | Procuring Entity or Public Sector Undertaking (PSU). |
| `Tender` | `id` | `IWD/IE/26-27/RT2/E-49` | Real scraped procurement tender from GeM or CPPP. |
| `Client` | `id` | `client_surya`, `client_kaveri` | Synthetic Indian contractor profile bidding on public works. |
| `WorkCategory` | `name` | `Electrical`, `Civil Works` | Broad procurement trade discipline. |
| `Specialization`| `name` | `HT Substation Erection` | Domain-specific technical capabilities. |
| `Certification` | `name` | `BIS IS-7098`, `ISO 9001:2015` | Statutory technical and quality accreditations. |
| `Brand` | `name` | `Havells`, `Polycab`, `Cisco` | OEM manufacturers and equipment makers (`is_demo_sample: true`). |
| `Product` | `name` | `LT/HT Armoured Cables` | Specific physical goods or bill-of-quantities line items. |
| `EnlistmentClass`| `code` | `CPWD-CLASS-I-CIVIL` | Official government contractor pre-qualification grade. |
| `Region` | `name` | `Karnataka`, `Maharashtra` | Indian State or Union Territory governing territorial GST. |
| `JVConsortium` | `id` | `jv_client_kaveri_client_surya...` | Synthesized Joint Venture entity formed for turnkey bids. |
| `AgentDecision` | `id` | `dec_seed_bharat_it` | Immutable audit record of autonomous agent evaluation. |
| `SystemMeta` | `key` | `scraper_status` | Metadata tracking database initialization and cold-start memory. |

---

### 3.2 Relationship Edge Taxonomy

| Relationship Type | Source Node | Target Node | Key Edge Properties | Business Semantics |
| :--- | :--- | :--- | :--- | :--- |
| `HAS_DEPARTMENT` | `Ministry` | `Department` | — | Administrative departmental hierarchy. |
| `ISSUED` | `Department` | `Tender` | — | Tender issuance by procuring authority. |
| `LOCATED_IN` | `Tender` | `Region` | — | Project delivery state jurisdiction. |
| `IN_CATEGORY` | `Tender` | `WorkCategory` | — | Mandatory trade classification. |
| `REQUIRES_SPECIALIZATION`| `Tender` | `Specialization` | — | Mandatory operational qualification. |
| `REQUIRES_CERT` | `Tender` | `Certification` | `valid_until` | Mandatory technical quality certification. |
| `PREFERS_BRAND` | `Tender` | `Brand` | `strict_auth_required` (bool) | OEM brand preference with mandatory authorization gate. |
| `REQUIRES_PRODUCT` | `Tender` | `Product` | `quantity`, `unit`, `requires_oem_or_auth` | Line-item product requirement. |
| `REQUIRES_ENLISTMENT` | `Tender` | `EnlistmentClass`| — | Government contractor enlistment tier. |
| `WORKS_IN` | `Client` | `WorkCategory` | — | Contractor primary trade discipline. |
| `HAS_SPECIALIZATION` | `Client` | `Specialization` | — | Contractor specialized technical competence. |
| `HOLDS_CERT` | `Client` | `Certification` | `valid_until` (epoch timestamp) | Valid accreditation with expiration tracking. |
| `AUTHORIZED_FOR` | `Client` | `Brand` | `role`, `territory`, `valid_until` | OEM vendor or distributor authorization. |
| `SUPPLIES` | `Client` | `Product` | `is_oem`, `facility_name`, `monthly_capacity` | Manufacturing and supply capabilities. |
| `ENLISTED_AS` | `Client` | `EnlistmentClass`| `grade`, `valid_until` | Active government contractor enlistment. |
| `OPERATES_IN` | `Client` | `Region` | `gstin`, `gst_valid` (bool), `filing_status` | State-level tax and business registration. |
| `MATCHED_TENDER` | `Client` | `Tender` | `match_score`, `match_type`, `status`, `last_alert_sent` | Operational state tracking (cooldown & outcome). |
| `BID_HISTORY` | `Client` | `Tender` | `outcome` (`WON`/`LOST`), `bid_amount`, `won_at` | Historical bidding record for learning & lookalike anchors. |
| `DEPARTMENT_AFFINITY` | `Client` | `Department` | `wins`, `losses`, `win_rate`, `affinity_weight` | Adaptive learning graph weight. |
| `PARTNERSHIP_AFFINITY` | `Client` | `Client` | `proposals`, `wins`, `affinity_score` | Inter-contractor syndicate collaboration record. |
| `LEAD_IN_CONSORTIUM` | `Client` | `JVConsortium` | — | Designated Lead Managing Partner in syndicate. |
| `PARTNER_IN_CONSORTIUM`| `Client` | `JVConsortium` | — | Technical/Consortium Partner in syndicate. |
| `FORMED_FOR_TENDER` | `JVConsortium`| `Tender` | — | Specific tender for which the JV was synthesized. |
| `FOR_CLIENT` | `AgentDecision`| `Client` | — | Client recipient of the evaluated decision. |
| `EVALUATED_TENDER` | `AgentDecision`| `Tender` | — | Tender evaluated by the autonomous agent. |

---

## 4. Multi-Hop Graph Traversal Patterns & OpenCypher Implementations

### Pattern A: Direct Multi-Criteria Eligibility Gate with Dynamic Coverage Scoring

Evaluates whether a single contractor satisfies 100% of financial, technical, regional, and statutory constraints independently, computing a dynamic match score based on requirement coverage depth and historical department affinity.

```cypher
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
```

---

### Pattern B: 5-Hop Lookalike Peer Discovery with Minimum 2 Distinct Anchors

Uncovers competitor lookalikes who have not bid with this specific procuring department before, but mirror the multi-dimensional capability topology of historical winning contractors in the department. To prevent de-anonymization and spurious single-match correlation, the traversal:
1. Constrains past contracts (`past_t`) to the **exact same WorkCategory** as the target tender.
2. Applies **Pattern A's statutory hard gates** (solvency, GSTIN, work category, valid certifications, brand authorizations, and 48-hour alert cooldown) to the peer.
3. Groups by `(peer, anchor)`, requiring at least **$k \ge 2$ shared capabilities per winning anchor**.
4. Requires at least **$\ge 2$ distinct supporting winning anchors** before emitting any peer recommendation.
5. Employs a strict **Privacy Shield**: returns generic anonymized benchmark counts (`supporting_anchors`, `total_shared_caps`) with zero leakage of anchor corporate identity, turnover, or contract IDs.

$$\text{Target Tender } (wc) \leftarrow \text{Dept} \rightarrow \text{Past Won Tender } (wc) \leftarrow \text{Anchor Winners } (\ge 2) \rightarrow \text{Capabilities } (\ge 2/\text{anchor}) \leftarrow \text{Discovered Peer}$$

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

> [!IMPORTANT]
> **Privacy Shield Guarantee**: The Cypher query strictly redacts the anchor's corporate name, turnover, and past contract references at the graph RETURN layer (`"[Generic Peer Benchmark - Identity Shielded]"`). The peer contractor receives an alert highlighting high-level benchmark alignment without disclosing competitor identity, contract numbers, or individual capabilities.

---

### Pattern C: Multi-Discipline Joint Venture (JV) Consortium Synthesis

Under standard Indian public procurement norms, solo contractors cannot form a JV if they can independently satisfy all criteria. JVs are permissible for large composite turnkey projects where individual contractors fall short financially or technically, but their combination satisfies 100% of criteria:

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

When the user records an alert outcome (`Won` or `Lost`), the graph dynamically updates edge affinities using a Laplace-smoothed prior ($p_0 = 0.50$), boosting or penalizing future match scores without cold-start spikes:

$$\text{Win Rate} = \begin{cases} 0.0 & \text{if } \text{Wins} + \text{Losses} = 0 \\ \frac{\text{Wins}}{\text{Wins} + \text{Losses}} & \text{otherwise} \end{cases}$$

$$\text{Affinity Weight} = \left(\frac{\text{Wins} + 1}{\text{Wins} + \text{Losses} + 2} - 0.50\right) \times 0.50$$

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
> **Idempotency Protection & Double-Click Guard**: Because the Cypher statement executes increments based on passed deltas, double-click protection is enforced deterministically by the Python MCP layer before executing the query:
> ```python
> # Idempotency check in mcp_server/server.py:
> existing_check = graph.query(
>     "MATCH (c:Client {id: $client_id})-[m:MATCHED_TENDER]->(t:Tender {id: $tender_id}) RETURN m.status",
>     {"client_id": client_id, "tender_id": tender_id}
> )
> if prev_status == clean_outcome:
>     logger.info("Outcome already recorded. Idempotent skip.")
>     return json.dumps({"success": True, "idempotent_skip": True, ...})
> ```
> For tenders lacking an issuing department (common on raw CPPP portals), the engine cleanly returns `status: "NO_DEPARTMENT"` without crashing.

---

### Pattern E: 48-Hour Alert Cooldown Enforcement

Prevents alert fatigue across recurring cron matching schedules by tracking notification timestamps directly on `[:MATCHED_TENDER]` edges:

```cypher
MATCH (c:Client {id: $client_id})-[r:MATCHED_TENDER]->(t:Tender {id: $tender_id})
WHERE r.status = 'ALERTED' AND ($now - r.last_alert_sent) < 172800
RETURN r.status, (172800 - ($now - r.last_alert_sent)) AS seconds_remaining
```

---

### Pattern F: Constrained Shortest Path Exploration (Label Whitelisted & Directed with Privacy Shield)

Surfaces shortest relationship paths between any two graph entities. Node labels are strictly validated against a server-side whitelist (`ALLOWED_LABELS = {"Client", "Tender", "Department", "Ministry", "Region", "WorkCategory", "Certification", "Brand", "Product", "EnlistmentClass", "Specialization"}`), rejecting arbitrary label injections. To comply with FalkorDB's directed graph traversal engine, paths are evaluated forward and reverse in `WITH` clauses, combined via `coalesce()`, and filtered to strictly exclude competitor bid histories and match records:

```cypher
MATCH (s:Client {id: $start_id})
MATCH (t:Department {id: $target_id})
WITH shortestPath((s)-[*..3]->(t)) AS path_fwd,
     shortestPath((t)-[*..3]->(s)) AS path_rev
WITH coalesce(path_fwd, path_rev) AS path
WHERE path IS NOT NULL
  AND NONE(r IN relationships(path) WHERE type(r) IN ['BID_HISTORY', 'MATCHED_TENDER'])
RETURN [n IN nodes(path) | {id: coalesce(n.id, n.name, n.code), label: labels(n)[0]}],
       [r IN relationships(path) | type(r)]
LIMIT 5
```

> [!NOTE]
> **Lookalike Score Boost Application**: In the end-to-end matching pipeline, the Cypher traversal evaluates multi-hop capability mirroring and returns generic benchmark metrics (`supporting_anchors`, `total_shared_caps`). The additional lookalike boost (`+0.15` for 2 anchors, `+0.20` for $\ge 3$ anchors) is applied downstream by the AI agent layer in Python (`mcp_server/server.py` and `agent/langgraph_workflow.py`), keeping the database query focused strictly on topological filtering.

---

## 5. The 5-Stage CPWD/GeM JV Decision Tree

When a complementary syndicate is synthesized in FalkorDB, it is evaluated across a deterministic **5-Stage Statutory Decision Tree** before persistence:

```mermaid
flowchart TD
    S1{"Stage 1: Solo Disqualification Gate\nDoes either partner satisfy turnover alone?"}
    S1 -->|Yes| D1["DISQUALIFIED\nSolo contractor must bid alone under public procurement rules"]
    S1 -->|No| S2{"Stage 2: Financial Aggregation Gate\nCombined Turnover >= Tender Threshold?"}

    S2 -->|No| D2["DISQUALIFIED\nInadequate aggregated financial turnover"]
    S2 -->|Yes| S3{"Stage 3: Capability Union Gate\nUnion covers 100% of categories, brands & certs?"}

    S3 -->|No| D3["DISQUALIFIED\nUnmet technical specifications in BOQ union"]
    S3 -->|Yes| S4{"Stage 4: Regional Compliance Gate\nActive GSTIN in tender region & zero blacklisting?"}

    S4 -->|No| D4["DISQUALIFIED\nDebarment flag or invalid state tax registration"]
    S4 -->|Yes| S5["Stage 5: Consortium Governance Recommendation\nDesignate 60% Lead + 40% Consortium Partner"]
    S5 --> Persist["Persist :JVConsortium node & link edges in FalkorDB"]
```

Sample persisted `decision_tree_json` structure on `:JVConsortium` node:
```json
{
  "stage1_solo_disqualification": {
    "title": "Stage 1: Solo Disqualification Gate",
    "gate_passed": true,
    "lead_turnover_cr": 22.0,
    "partner_turnover_cr": 9.5,
    "tender_turnover_cr": 28.0,
    "reasoning": "Neither contractor meets the ₹28.0 Cr threshold individually. JV is legally permissible."
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

## 6. Synthetic Indian Enterprise Contractor Roster (Benchmark Profiles)

The seeder initializes **12 synthetic Indian enterprise contractor profiles** designed to benchmark diverse multi-hop procurement scenarios:

```
┌──────────────────────────────┬───────────────────────────────────────────────┬────────────────┬──────────┬─────────────┐
│ Client ID                    │ Company Name                                  │ 3-Yr Turnover  │ MSME?    │ Class       │
├──────────────────────────────┼───────────────────────────────────────────────┼────────────────┼──────────┼─────────────┤
│ client_surya                 │ Surya Wire & Switchgear Pvt Ltd               │ ₹9.50 Cr       │ Yes      │ Electrical  │
│ client_apex                  │ Apex Electricals & Cables Ltd                 │ ₹12.00 Cr      │ No       │ Electrical  │
│ client_kaveri                │ Kaveri Civil & Structural Infra Ltd           │ ₹22.00 Cr      │ No       │ Civil       │
│ client_lakshya_civil         │ Lakshya Highway & Infrastructure Ltd          │ ₹195.00 Cr     │ No       │ Heavy Civil │
│ client_bharat_it             │ Bharat Digital Networks & Systems Ltd         │ ₹55.00 Cr      │ No       │ IT Hardware │
│ client_vardhan_hvac          │ Vardhan Turnkey HVAC Engineers LLP            │ ₹38.00 Cr      │ No       │ HVAC & Mech │
│ client_garuda_furn           │ Garuda Workspaces & Modular Turnkey Ltd       │ ₹85.00 Cr      │ No       │ Furniture   │
│ client_meditech              │ Meditech LifeSciences & Hospital Solutions    │ ₹28.00 Cr      │ No       │ Healthcare  │
│ client_tarun_solar           │ Tarun CleanTech Solar EPC Solutions Ltd       │ ₹145.00 Cr     │ No       │ Solar EPC   │
│ client_zenith                │ Zenith Railtech & Telecom Systems Ltd         │ ₹18.50 Cr      │ No       │ Rail Telecom│
│ client_kalyani_msme          │ Kalyani Micro Steels & Heavy Fabrication      │ ₹7.50 Cr       │ Yes      │ MSME Supply │
│ client_defaulter             │ Defaulter Infrastructure Corp                 │ ₹15.00 Cr      │ No       │ Blacklisted │
└──────────────────────────────┴───────────────────────────────────────────────┴────────────────┴──────────┴─────────────┘
```

> [!NOTE]
> `client_defaulter` has `is_blacklisted = true`. Direct match and lookalike queries filter this node out immediately (`WHERE c.is_blacklisted = false`), enforcing statutory procurement debarment checks. All client identities and financials are synthetic demonstration records created for hackathon benchmarking.

---

## 7. Operational CLI Commands & Diagnostics

### 7.1 Re-seeding the Database
```bash
# Non-destructive seed (preserves Won/Lost history and affinities if already seeded)
python -m db.seed_graph

# Explicit force reset (clears the graph and seeds fresh benchmark state)
python -m db.seed_graph --force
# or
FORCE_RESET=true python -m db.seed_graph
```

### 7.2 Connection Testing & Latency Diagnostics
```python
from db.connection import test_connection

result = test_connection()
print(f"Status: {result['status']}, Latency: {result['latency_ms']}ms, Graphs: {result['graphs']}")
```

### 7.3 Schema Re-indexing
```python
from db.connection import get_graph
from db.schema import initialize_schema

graph = get_graph()
summary = initialize_schema(graph)
print(f"Created: {len(summary['created'])}, Existing: {len(summary['existing'])}")
```

---

## 8. Automated Verification & Test Suite Coverage

The database module, FastMCP boundary, and Cypher traversals are verified across all 7 test suites totaling **42 tests (100% passing)**:

1. **`tests/test_rule12_and_cypher_integrity.py` (9 Tests)**:
   - `test_readme_cypher_queries_syntax_and_execution`: Executes Patterns A, B, and C directly against FalkorDB, validating openCypher syntax, list comprehensions, and score computations.
   - `test_laplace_smoothed_learning_and_double_click_idempotency`: Verifies Laplace smoothing math ($p_0 = 0.50$), evaluation order in multi-step `WITH` clauses, and double-click idempotency skip.
   - `test_lookalike_peer_alert_and_email_zero_anchor_leakage`: Proves that lookalike peer alerts contain zero anchor corporate name, turnover, or past contract reference.
   - `test_pattern_f_explore_paths_syntax_and_whitelist`: Validates server-side label whitelisting, malicious injection blocking, and directed `shortestPath` traversal with `coalesce(path_fwd, path_rev)`.
   - `test_pattern_d_tenders_without_department_handling`: Validates that unassigned tenders (common on CPPP) return `NO_DEPARTMENT` without crashing or breaking feedback loops.
   - `test_pattern_a_credential_gating_rejects_missing_credentials`: Verifies that clients missing required certifications or brand authorizations are blocked.
   - `test_pattern_a_and_c_null_requirements_do_not_drop_qualifying_clients`: Verifies that tenders with null requirement fields do not drop qualifying contractors.
   - `test_pattern_f_explore_paths_privacy_shield_blocks_competitor_edges`: Validates that topological shortest path graph exploration filters out competitor `BID_HISTORY` and `MATCHED_TENDER` edges.
   - `test_pattern_b_lookalike_peer_eligibility_and_cooldown_gating`: Verifies that lookalike peers must pass blacklist, GST, turnover, and 48-hour alert cooldown gates.

2. **`tests/test_email_alerting_hackathon.py` (4 Tests)**:
   - `test_all_clients_have_hackathon_demo_email`: Verifies that all 12 synthetic client nodes maintain `hackathon-demo@outlook.com`.
   - `test_send_single_alert_endpoint_payload`: Asserts alert payload contains client name, tender name, formatted INR value, plus points, and reason chosen.
   - `test_lookalike_privacy_shield_never_reveals_peer`: Validates that peer alerts and emails redact competitor names, turnover figures, and past contract references.
   - `test_batch_alert_send_endpoint`: Dispatches batch alerts for all active tender matches to the outbox log.

3. **`tests/test_phase1_mcp_and_graph.py` (7 Tests)**:
   - Validates schema idempotency, enricher scraping/heartbeat, direct and 5-hop lookalike matching, JV consortium discovery, 2-day cooldown enforcement, Won/Lost outcome learning, and read-only diagnostic Cypher execution.

4. **`tests/test_phase2_agent_and_api.py` (6 Tests)**:
   - Validates AST zero-driver database isolation across `agent/` and `api/`, live MCP client handshake/discovery, tender ingestion pull endpoints, matching loops, and outcome feedback.

5. **`tests/test_phase3_ui_and_e2e_workflow.py` (5 Tests)**:
   - Validates frontend static asset serving, demo reset/seeding via MCP, tender enrichment and ingestion pipeline, end-to-end judge workflow with 48h time-jump simulations, and AST zero-driver isolation.

6. **`tests/test_phase4_jv_and_langgraph.py` (5 Tests)**:
   - Validates AST zero-driver isolation, tender estimated values and turnover requirements ($>0$), JV consortium graph persistence, 5-stage decision tree evaluation, JV outcome learning loops, and full multi-node LangGraph StateGraph execution.

7. **`tests/test_phase5_communication_agent.py` (6 Tests)**:
   - Validates AST zero-driver database isolation in `agent/communication_agent.py`, NVIDIA Nemotron 3.5 model targeting, single and batch email drafting, and peer privacy masking.
