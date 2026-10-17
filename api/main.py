
import os
import time
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware

from agent.mcp_agent import BidGraphMCPAgent
from agent.models import (
    DashboardState,
    PullTendersResponse,
    MatchingLoopRequest,
    MatchingLoopResponse,
    OutcomeFeedbackRequest,
    OutcomeFeedbackResponse,
    JVOutcomeFeedbackRequest,
    JVOutcomeFeedbackResponse,
    EmailDraftRecord,
    DraftEmailRequest,
    DraftAllEmailsResponse,
    SendAlertRequest,
    SendAlertResponse,
    SendAllAlertsResponse,
)

logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="BidGraphAI Tender Intelligence API",
    description="Agentic procurement intelligence system powered by FalkorDB graph traversals and the Model Context Protocol (MCP).",
    version="2.0.0",
)

_last_endpoint_calls: Dict[str, float] = {}

def _check_rate_limit(endpoint_key: str, min_interval_seconds: float) -> None:
    
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 
    now = time.time()
    last_call = _last_endpoint_calls.get(endpoint_key, 0.0)
    elapsed = now - last_call
    if elapsed < min_interval_seconds:
        wait_seconds = round(min_interval_seconds - elapsed, 1)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {endpoint_key}. Please wait {wait_seconds}s before retrying."
        )
    _last_endpoint_calls[endpoint_key] = now


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


agent = BidGraphMCPAgent()


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint verifying live MCP server tool discovery."""
    try:
        tools = await agent.list_mcp_tools()
        return {
            "status": "ok",
            "engine": "FalkorDB via MCP",
            "protocol": "Model Context Protocol (FastMCP)",
            "mcp_tools_count": len(tools),
            "mcp_tools_registered": [t["name"] for t in tools],
        }
    except Exception as exc:
        logger.error("Health check MCP discovery failed: %s", exc)
        return {
            "status": "degraded",
            "engine": "FalkorDB via MCP",
            "error": "MCP database discovery degraded",
        }


@app.get("/api/dashboard", response_model=DashboardState)
async def get_dashboard(
    client_id: Optional[str] = Query(None, description="Filter alerts for a specific client ID"),
    current_timestamp: Optional[int] = Query(None, description="Override timestamp for cooldown calculations"),
) -> DashboardState:
    """
    Returns the complete live dashboard state:
    - Top banner scraper sync status & active tenders count
    - Alert history feed with 2-day cooldown badges & agent reasoning traces
    - Dynamic learned affinities (Department & Category weights)
    - Graph visualization topological snapshot (nodes and links)
    """
    try:
        return await agent.get_dashboard_state(
            client_id=client_id,
            current_timestamp=current_timestamp
        )
    except Exception as exc:
        logger.error("Failed to fetch dashboard state: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard: {exc}")


@app.post("/api/tenders/pull", response_model=PullTendersResponse)
async def pull_tenders_data(
    payload: Optional[Dict[str, Any]] = Body(default=None)
) -> PullTendersResponse:
    """
    Triggered by the UI 'Pull Tender Data from DB' button.
    Fetches all active tenders and scraper sync status from FalkorDB exclusively via MCP.
    """
    status_filter = "ACTIVE"
    if payload and "status_filter" in payload:
        status_filter = payload["status_filter"]

    try:
        return await agent.pull_tenders_from_db(status_filter=status_filter)
    except Exception as exc:
        logger.error("Failed to pull tenders: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to pull tender data: {exc}")


@app.post("/api/agent/match", response_model=MatchingLoopResponse)
async def run_tender_matching(
    request: Optional[MatchingLoopRequest] = Body(default_factory=MatchingLoopRequest)
) -> MatchingLoopResponse:
    """
    Triggered by the UI 'Run Tender Matching Loop' button.
    Runs multi-hop eligibility filtering, 2-day cooldown checks, 5-hop lookalike peer discovery,
    and Joint Venture (JV) consortium matching, dispatching alerts with reasoning traces.
    """
    try:
        req = request or MatchingLoopRequest()
        return await agent.run_tender_matching_loop(
            tender_ids=req.tender_ids,
            min_score_threshold=req.min_score_threshold,
            current_timestamp=req.current_timestamp,
        )
    except Exception as exc:
        logger.error("Tender matching loop failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Matching loop failed: {exc}")


@app.post("/api/alerts/outcome", response_model=OutcomeFeedbackResponse)
async def record_alert_outcome(
    request: OutcomeFeedbackRequest = Body(...)
) -> OutcomeFeedbackResponse:
    """
    Triggered by the 'Won' and 'Lost' outcome feedback buttons on any tender alert.
    Updates :MATCHED_TENDER, logs :BID_HISTORY, and executes the adaptive graph learning loop.
    """
    clean_outcome = request.outcome.strip().upper()
    if clean_outcome not in ["WON", "LOST"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome '{request.outcome}'. Expected 'WON' or 'LOST'."
        )

    try:
        return await agent.record_outcome_feedback(
            client_id=request.client_id,
            tender_id=request.tender_id,
            outcome=clean_outcome,
            feedback_notes=request.feedback_notes,
            current_timestamp=request.current_timestamp,
        )
    except Exception as exc:
        logger.error("Failed to record outcome feedback: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to record outcome: {exc}")


@app.post("/api/jv/outcome", response_model=JVOutcomeFeedbackResponse)
async def record_jv_outcome_endpoint(
    request: JVOutcomeFeedbackRequest = Body(...)
) -> JVOutcomeFeedbackResponse:
    """
    Triggered by the 'Won' and 'Lost' outcome feedback buttons on any Joint Venture consortium.
    
    """
    clean_outcome = request.outcome.strip().upper()
    if clean_outcome not in ["WON", "LOST"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome '{request.outcome}'. Expected 'WON' or 'LOST'."
        )

    try:
        return await agent.record_jv_outcome(
            jv_id=request.jv_id,
            outcome=clean_outcome,
            current_timestamp=request.current_timestamp,
        )
    except Exception as exc:
        logger.error("Failed to record JV outcome: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to record JV outcome: {exc}")


@app.post("/api/agent/langgraph/run", response_model=MatchingLoopResponse)
async def run_langgraph_agent_endpoint(
    request: Optional[MatchingLoopRequest] = Body(default_factory=MatchingLoopRequest)
) -> MatchingLoopResponse:
    """
    Executes the multi-agent cognitive pipeline using LangGraph, LangChain, and NVIDIA Nemotron 3.5.
    Coordinates tender triage, FalkorDB multi-hop graph traversals, and executive syndicate synthesis.
    """
    try:
        from agent.langgraph_workflow import BidGraphLangGraphOrchestrator
        orchestrator = BidGraphLangGraphOrchestrator(agent=agent)
        req = request or MatchingLoopRequest()
        return await orchestrator.run(
            current_timestamp=req.current_timestamp,
            min_score_threshold=req.min_score_threshold,
        )
    except Exception as exc:
        logger.exception("LangGraph agent run failed: %s", exc)
        if hasattr(exc, "exceptions"):
            for sub in exc.exceptions:
                logger.error("SUB-EXCEPTION: %r", sub)
        raise HTTPException(status_code=500, detail=f"LangGraph execution failed: {exc}")


@app.post("/api/pipeline/enrich-and-ingest")
async def enrich_and_ingest_tender_endpoint(
    payload: Optional[Dict[str, Any]] = Body(default=None)
) -> Dict[str, Any]:
    """
    Scrapes live Indian government tender listings (GeM & CPPP), enriches them with trade,
    BOQ, and financial eligibility criteria, and upserts them into FalkorDB via MCP.
    If a specific single tender payload is provided, enriches and ingests that single tender.
    """
    try:
        return await agent.ingest_sample_tender(payload)
    except Exception as exc:
        logger.error("Failed to enrich and ingest tender: %s", exc)
        raise HTTPException(status_code=500, detail=f"Enrichment/Ingestion failed: {exc}")


@app.post("/api/tenders/delete-all")
@app.delete("/api/tenders")
async def delete_all_tenders_endpoint() -> Dict[str, Any]:
    """
    Deletes all active tender records and stale match decisions from FalkorDB via MCP.
    Guarded with debounce rate-limiting to prevent malicious database wipes.
    """
    _check_rate_limit("tenders_delete_all", 10.0)
    try:
        return await agent.delete_all_active_tenders()
    except Exception as exc:
        logger.error("Failed to delete tenders: %s", exc)
        raise HTTPException(status_code=500, detail=f"Delete tenders failed: {exc}")


@app.post("/api/demo/reset")
async def reset_demo_graph_endpoint() -> Dict[str, Any]:
    """
    Resets and re-seeds the FalkorDB graph back to the deterministic initial benchmark state.
    Executed strictly through the MCP tool reset_and_seed_demo_graph.
    Guarded with debounce rate-limiting to prevent malicious graph reset thrashing.
    """
    _check_rate_limit("demo_reset", 10.0)
    try:
        return await agent.reset_and_seed_demo()
    except Exception as exc:
        logger.error("Failed to reset demo graph: %s", exc)
        raise HTTPException(status_code=500, detail=f"Reset demo graph failed: {exc}")


@app.post("/api/agent/draft-email", response_model=EmailDraftRecord)
async def draft_alert_email_endpoint(
    request: DraftEmailRequest = Body(...)
) -> EmailDraftRecord:
    """
    Invokes the Communication Agent powered by nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4 (Hugging Face)
    to draft a tailored alerting email for the specified client and tender match.
    Strictly pulls recipient email from the FalkorDB Client node.
    """
    try:
        from agent.communication_agent import CommunicationAgent
        comm_agent = CommunicationAgent(mcp_agent=agent)
        return await comm_agent.draft_alert_email(
            client_id=request.client_id,
            tender_id=request.tender_id,
        )
    except Exception as exc:
        logger.error("Failed to draft alert email: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to draft alert email: {exc}")


@app.post("/api/agent/draft-all-emails", response_model=DraftAllEmailsResponse)
async def draft_all_alert_emails_endpoint() -> DraftAllEmailsResponse:
    """
    Invokes the Communication Agent to draft tailored alerting emails for all currently dispatched
    alerts across FalkorDB using nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4 (Hugging Face).
    Guarded with debounce rate-limiting to protect LLM credit quotas.
    """
    _check_rate_limit("draft_all_emails", 5.0)
    try:
        from agent.communication_agent import CommunicationAgent
        comm_agent = CommunicationAgent(mcp_agent=agent)
        drafts = await comm_agent.draft_all_active_alert_emails()
        return DraftAllEmailsResponse(
            total_drafted=len(drafts),
            drafts=drafts,
            generated_at=int(time.time()),
        )
    except Exception as exc:
        logger.error("Failed to draft all alert emails: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to draft alert emails: {exc}")


@app.post("/api/agent/send-alert", response_model=SendAlertResponse)
async def send_alert_email_endpoint(
    request: SendAlertRequest = Body(...)
) -> SendAlertResponse:
    """
    Sends an executive tender alert email directly to the client's registered email
    (hackathon-demo@outlook.com) using the AI Communication Agent.
    Strictly protects peer contractor identities in lookalike hop matches.
    """
    try:
        from agent.communication_agent import CommunicationAgent
        comm_agent = CommunicationAgent(mcp_agent=agent)
        record = await comm_agent.send_alert_email(
            client_id=request.client_id,
            tender_id=request.tender_id,
        )
        return SendAlertResponse(
            success=True,
            message=f"Alert email successfully dispatched to {record.dispatched_to}",
            recipient=record.dispatched_to or "hackathon-demo@outlook.com",
            record=record,
        )
    except Exception as exc:
        logger.error("Failed to send alert email: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to send alert email: {exc}")


@app.post("/api/agent/send-all-alerts", response_model=SendAllAlertsResponse)
async def send_all_alert_emails_endpoint() -> SendAllAlertsResponse:
    """
    Dispatches executive tender alert emails to all matched clients at hackathon-demo@outlook.com.
    Guarded with debounce rate-limiting to prevent outbound email flood.
    """
    _check_rate_limit("send_all_alerts", 5.0)
    try:
        from agent.communication_agent import CommunicationAgent
        comm_agent = CommunicationAgent(mcp_agent=agent)
        records = await comm_agent.send_all_active_alert_emails()
        recipient = records[0].dispatched_to if records else "hackathon-demo@outlook.com"
        return SendAllAlertsResponse(
            total_sent=len(records),
            recipient=recipient,
            message=f"Successfully dispatched {len(records)} tender alert emails to {recipient}",
            records=records,
            dispatched_at=int(time.time()),
        )
    except Exception as exc:
        logger.error("Failed to dispatch batch alert emails: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to dispatch batch alert emails: {exc}")


# Mount Static Frontend Dashboard (Executive Command Center)
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_frontend_dir = os.path.join(_base_dir, "frontend")

if os.path.exists(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/")
    async def serve_dashboard():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/styles.css")
    async def serve_styles():
        return FileResponse(os.path.join(_frontend_dir, "styles.css"))

    @app.get("/app.js")
    async def serve_app_js():
        return FileResponse(os.path.join(_frontend_dir, "app.js"))

