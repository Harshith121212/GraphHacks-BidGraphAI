"""Pydantic schemas for Agent runs, tool traces, alert payloads, and API contracts."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    status: str = "success"
    error: Optional[str] = None


class ScraperStatus(BaseModel):
    last_scraped_at: Optional[int] = None
    total_tenders_ingested: int = 0
    scraper_source: Optional[str] = None


class DepartmentAffinitySummary(BaseModel):
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    affinity_weight: float = 0.0


class AlertRecord(BaseModel):
    client_id: str
    client_name: str
    tender_id: str
    tender_title: str
    department_name: str
    ministry_name: str
    tender_amount: float
    match_score: float
    match_type: str
    status: str  # ALERTED, WON, LOST
    alert_count: int
    first_matched_at: Optional[int] = None
    last_alert_sent: Optional[int] = None
    cooldown_active: bool = False
    cooldown_seconds_remaining: int = 0
    reasoning_trace: str
    path_summary: str
    department_affinity: Optional[DepartmentAffinitySummary] = None
    evaluating_agent: Optional[str] = None
    client_email: Optional[str] = "hackathon-demo@outlook.com"


class LearnedAffinity(BaseModel):
    client_id: str
    client_name: str
    target_entity: str
    affinity_type: str  # DEPARTMENT or CATEGORY
    wins: int
    losses: int
    win_rate: float
    affinity_weight: float
    updated_at: Optional[int] = None


class GraphSnapshot(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class JVConsortiumRecord(BaseModel):
    id: str
    tender_id: str
    tender_title: Optional[str] = None
    lead_id: str
    lead_name: str
    partner_id: str
    partner_name: str
    combined_turnover: float
    required_turnover: float
    synergy_score: float = 0.96
    status: str = "RECOMMENDED"  # RECOMMENDED, WON, LOST
    decision_tree: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[int] = None


class DashboardState(BaseModel):
    scraper_status: ScraperStatus
    active_tenders: List[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[AlertRecord] = Field(default_factory=list)
    learned_affinities: List[LearnedAffinity] = Field(default_factory=list)
    jv_consortiums: List[JVConsortiumRecord] = Field(default_factory=list)
    graph_snapshot: GraphSnapshot
    query_timestamp: int


class PullTendersResponse(BaseModel):
    scraper_status: ScraperStatus
    total_tenders: int
    tenders: List[Dict[str, Any]] = Field(default_factory=list)
    mcp_tool_trace: ToolCallTrace


class MatchingLoopRequest(BaseModel):
    tender_ids: Optional[List[str]] = None
    min_score_threshold: float = 0.35
    current_timestamp: Optional[int] = None


class AgentDecisionRecord(BaseModel):
    client_id: str
    tender_id: str
    match_type: str
    match_score: float
    action: str  # ALERT_SENT or ALERT_SKIPPED
    reason: Optional[str] = None
    reasoning_trace: str
    path_summary: str
    evaluating_agent: Optional[str] = None


class MatchingLoopResponse(BaseModel):
    tenders_evaluated: int
    direct_or_lookalike_matches_found: int
    jv_consortiums_found: int
    alerts_dispatched: int
    alerts_skipped_cooldown_or_terminal: int
    decisions: List[AgentDecisionRecord] = Field(default_factory=list)
    mcp_tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    executed_at: int
    agents_active: Optional[List[str]] = None
    parallel_batches_executed: Optional[int] = None
    alpha_tenders_count: Optional[int] = 0
    beta_tenders_count: Optional[int] = 0
    alpha_tender_ids: Optional[List[str]] = Field(default_factory=list)
    beta_tender_ids: Optional[List[str]] = Field(default_factory=list)
    overlap_count: Optional[int] = 0


class OutcomeFeedbackRequest(BaseModel):
    client_id: str
    tender_id: str
    outcome: str  # WON or LOST
    feedback_notes: str = ""
    current_timestamp: Optional[int] = None


class OutcomeFeedbackResponse(BaseModel):
    success: bool
    client_id: str
    tender_id: str
    outcome: str
    resolved_at: int
    department_affinity: Optional[Dict[str, Any]] = None
    category_affinities: List[Dict[str, Any]] = Field(default_factory=list)
    mcp_tool_trace: ToolCallTrace


class JVOutcomeFeedbackRequest(BaseModel):
    jv_id: str
    outcome: str  # WON or LOST
    current_timestamp: Optional[int] = None


class JVOutcomeFeedbackResponse(BaseModel):
    success: bool
    jv_id: str
    lead_name: str
    partner_name: str
    status: str
    wins: int
    losses: int
    affinity_score: float
    resolved_at: int
    mcp_tool_trace: ToolCallTrace


class EmailDraftRecord(BaseModel):
    client_id: str
    client_name: str
    client_email: Optional[str] = None
    email_status: str  # "CONFIGURED" or "PENDING_CLIENT_NODE_UPDATE"
    tender_id: str
    tender_name: str
    tender_title: Optional[str] = None
    scope_of_work: str
    tender_value: float
    tender_value_formatted: str
    tender_end_date: str
    tender_deadline: Optional[str] = None
    match_score: float
    match_score_pct: int
    fit_score_pct: Optional[float] = None
    plus_points: List[str] = Field(default_factory=list)
    reason_chosen: Optional[str] = None
    subject: str
    email_subject: Optional[str] = None
    body_plain: str
    email_body: Optional[str] = None
    body_html: str
    model_used: str = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
    generated_at: int
    delivery_status: str = "SENT"
    dispatched_to: Optional[str] = "hackathon-demo@outlook.com"
    dispatched_at: Optional[int] = None

    def __init__(self, **data):
        if "tender_title" not in data and "tender_name" in data:
            data["tender_title"] = data["tender_name"]
        if "tender_name" not in data and "tender_title" in data:
            data["tender_name"] = data["tender_title"]
        if "tender_deadline" not in data and "tender_end_date" in data:
            data["tender_deadline"] = data["tender_end_date"]
        if "tender_end_date" not in data and "tender_deadline" in data:
            data["tender_end_date"] = data["tender_deadline"]
        if "fit_score_pct" not in data and "match_score_pct" in data:
            data["fit_score_pct"] = float(data["match_score_pct"])
        if "match_score_pct" not in data and "fit_score_pct" in data:
            data["match_score_pct"] = int(data["fit_score_pct"])
        if "email_subject" not in data and "subject" in data:
            data["email_subject"] = data["subject"]
        if "subject" not in data and "email_subject" in data:
            data["subject"] = data["email_subject"]
        if "email_body" not in data and "body_plain" in data:
            data["email_body"] = data["body_plain"]
        if "body_plain" not in data and "email_body" in data:
            data["body_plain"] = data["email_body"]
        if "dispatched_to" not in data and "client_email" in data:
            data["dispatched_to"] = data["client_email"]
        super().__init__(**data)


class DraftEmailRequest(BaseModel):
    client_id: str
    tender_id: str


class DraftAllEmailsResponse(BaseModel):
    total_drafted: int
    drafts: List[EmailDraftRecord] = Field(default_factory=list)
    model_used: str = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
    generated_at: int


class SendAlertRequest(BaseModel):
    client_id: str
    tender_id: str


class SendAlertResponse(BaseModel):
    success: bool
    message: str
    recipient: str
    record: EmailDraftRecord


class SendAllAlertsResponse(BaseModel):
    total_sent: int
    recipient: str
    message: str
    records: List[EmailDraftRecord] = Field(default_factory=list)
    dispatched_at: int

