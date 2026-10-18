# BidGraphAI Security & Compliance Architecture

This document outlines the security, confidentiality, and infrastructure policies implemented in BidGraphAI.

---

## 1. Network & Database Transport Security (TLS)

BidGraphAI encrypts all communication with external managed graph databases (e.g., FalkorDB Cloud) over **TLS (Port 6379 / custom port)**.

### Known Cloud Infrastructure Constraint (TLS Verification)
- **Environment**: FalkorDB Cloud instances provision dynamic AWS nodes (e.g., `*.instance-xvrjb6bb8.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud`).
- **Constraint**: These dynamic endpoints do not present certificates signed with public wildcard SANs matching the AWS cluster URL.
- **Handling**:
  - In `db/connection.py`, encrypted transport over TLS is strictly maintained (`ssl=True`).
  - Certificate and hostname verification are enabled by default (`FALKORDB_SSL_VERIFY=true`). If the endpoint certificate does not validate, the connection fails rather than silently weakening verification.
  - A deployment can explicitly disable verification by setting:
    ```bash
    FALKORDB_SSL_VERIFY=false
    ```
    This leaves TLS encryption in place but does not authenticate the server certificate; use only when the endpoint cannot support strict verification and the risk is understood.

---

## 2. Competitor Privacy Shield (Procurement Competition Law)

Under Indian public procurement regulations (Competition Act 2002 & General Financial Rules), an intelligence platform must never facilitate anti-competitive information exchange or leak proprietary bidder data (such as corporate turnover, bid history, or margin strategy) to competing contractors.

### Implementation:
1. **Anchor Identity Withholding**:
   - Lookalike query results return counts and shared-capability totals, not anchor client IDs or past tender IDs.
   - The audit trace describes the aggregate signal and intentionally omits anchor identities. It does not rely on hashing client IDs as anonymization.
2. **Strict Redaction in Peer Alerts**:
   - The peer contractor receives an alert derived from capability alignment (specifications, GST, DPIIT local content), but **zero** anchor company name, 3-year turnover, or past contract reference is ever returned to or displayed for the peer.
3. **Automated Verification**:
   - Continuous test coverage (`tests/test_phase2_agent_and_api.py::test_privacy_shield_lookalike_peer_alert_anonymity`) programmatically asserts that no competitor's proprietary attributes exist in peer notifications.

---

## 3. Email Dispatch Security & Sandbox Allowlist

To prevent outbound spam, unintended customer alerts during judging, and network hang timeouts, the Communication Agent enforces strict sandboxing:

1. **Deterministic Recipient Redirection**:
   - Every outgoing email is routed exclusively to the hackathon demonstration address:
     `hackathon-demo@outlook.com`
   - Additional test inboxes may be explicitly configured via `ALLOWED_EMAIL_RECIPIENTS`.
2. **Provider Timeout Protection**:
   - External transactional mail APIs (Resend, SendGrid) are bounded to a **4.0-second timeout** with automatic fallback to local persistent delivery logging (`data/dispatched_alerts.jsonl`).
3. **Synthetic Identity Compliance (Hackathon Rule 6)**:
   - All seeded enterprise contractors, GSTINs, and seller IDs are synthetic mock entities created exclusively for benchmark evaluation.

---

## 4. Endpoint Protection & LLM Credit Quota Guards

To prevent unauthorized database wipes and API credit exhaustion when deployed on public cloud services (e.g. Render):

1. **Debounce Rate Limiting**:
   - `POST /api/demo/reset`: 10-second debounce.
   - `POST /api/tenders/delete-all`: 10-second debounce.
   - `POST /api/agent/draft-all-emails`: 5-second debounce.
   - `POST /api/agent/send-all-alerts`: 5-second debounce.
   - Requests exceeding these thresholds return `HTTP 429 Too Many Requests`.
2. **OpenRouter Sliding-Window LLM Rate Limiter**:
   - Bounded to a maximum of 40 calls per minute across Agent Alpha and Agent Beta.
   - When the sliding budget is exhausted, the engine automatically falls back to deterministic graph reasoning, ensuring uninterrupted platform availability with zero credit drain.
