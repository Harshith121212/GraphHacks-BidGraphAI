

import os
import time
import json
import hashlib
import logging
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from agent.mcp_agent import BidGraphMCPAgent
from agent.models import (
    MatchingLoopResponse,
    AgentDecisionRecord,
    ToolCallTrace,
)

logger = logging.getLogger(__name__)


class LangGraphAgentState(TypedDict):
    current_timestamp: int
    min_score_threshold: float
    active_tenders: List[Dict[str, Any]]
    direct_candidates: List[Dict[str, Any]]
    jv_consortiums: List[Dict[str, Any]]
    executive_strategy_insights: List[Dict[str, Any]]
    alerts_dispatched: int
    alerts_skipped: int
    decisions: List[Dict[str, Any]]
    tool_traces: List[Dict[str, Any]]
    errors: List[str]


def _extract_llm_text(content: Any) -> str:
    """Helper to extract clean text from LangChain message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(item.text)
        return "\n".join(parts).strip()
    return str(content).strip()


class BidGraphLangGraphOrchestrator:
    """
    Coordinates LangGraph StateGraph nodes with MCP tools and NVIDIA Nemotron 3.5.
    
    """

    def __init__(self, agent: Optional[BidGraphMCPAgent] = None):
        self.agent = agent or BidGraphMCPAgent()
        self.settings = get_settings()
        self._init_llm()

    def _init_llm(self):
        self.llm = None

    async def triage_active_procurement_node(self, state: LangGraphAgentState) -> Dict[str, Any]:
        """Node 1: Pulls active tenders from FalkorDB via MCP."""
        try:
            resp = await self.agent.pull_tenders_from_db(status_filter="ACTIVE")
            tenders = resp.tenders
            logger.info("LangGraph Node 1: Triaged %d active tenders.", len(tenders))
            return {
                "active_tenders": tenders,
                "tool_traces": [resp.mcp_tool_trace.model_dump()],
            }
        except Exception as exc:
            logger.error("LangGraph Node 1 failed: %s", exc)
            return {"active_tenders": [], "errors": state.get("errors", []) + [str(exc)]}

    async def falkordb_graph_matching_node(self, state: LangGraphAgentState) -> Dict[str, Any]:
        """Node 2: Executes native OpenCypher traversals via MCP for single & JV matches."""
        now = state.get("current_timestamp", int(time.time()))
        tenders = state.get("active_tenders", [])
        traces = list(state.get("tool_traces", []))
        direct_cands = []
        jv_list = []

        async with self.agent._connect_session() as session:
            for t in tenders:
                tid = t.get("id") or t.get("tender_id")

                # 1. Parameterized Template Tool 1: get_tender_requirements
                dept_id = None
                try:
                    req_data, r_trace = await self.agent._call_tool(
                        session,
                        "get_tender_requirements",
                        {"tender_id": tid}
                    )
                    traces.append(r_trace.model_dump())
                    dept_id = req_data.get("department_id")
                    t["_requirements"] = req_data
                except Exception as exc:
                    logger.warning("get_tender_requirements failed for %s: %s", tid, exc)

                # 2. Direct & 5-hop lookalike peer discovery
                try:
                    c_data, trace = await self.agent._call_tool(
                        session,
                        "discover_direct_and_lookalike_matches",
                        {"tender_id": tid, "current_timestamp": now}
                    )
                    traces.append(trace.model_dump())
                    for c in c_data.get("candidates", []):
                        c["_tender_ref"] = t
                        cid = c.get("client_id")
                        c_plan = ["get_tender_requirements"]

                        # 3. Parameterized Template Tool 2: check_client_coverage
                        try:
                            cov_data, cov_trace = await self.agent._call_tool(
                                session,
                                "check_client_coverage",
                                {"client_id": cid, "tender_id": tid}
                            )
                            traces.append(cov_trace.model_dump())
                            c["_coverage"] = cov_data
                            c_plan.append("check_client_coverage")
                        except Exception as exc:
                            logger.warning("check_client_coverage failed: %s", exc)

                        # 4. Parameterized Template Tool 3: get_department_lineage
                        if dept_id:
                            try:
                                lin_data, lin_trace = await self.agent._call_tool(
                                    session,
                                    "get_department_lineage",
                                    {"client_id": cid, "department_id": dept_id}
                                )
                                traces.append(lin_trace.model_dump())
                                c["_lineage"] = lin_data
                                c_plan.append("get_department_lineage")
                            except Exception as exc:
                                logger.warning("get_department_lineage failed: %s", exc)

                        # 5. Parameterized Template Tool 4: find_peer_clients
                        if c.get("lookalike_peers"):
                            try:
                                p_data, p_trace = await self.agent._call_tool(
                                    session,
                                    "find_peer_clients",
                                    {"client_id": cid, "tender_id": tid}
                                )
                                traces.append(p_trace.model_dump())
                                c["_peers"] = p_data
                                c_plan.append("find_peer_clients")
                            except Exception as exc:
                                logger.warning("find_peer_clients failed: %s", exc)

                        c_plan.append("dispatch_tender_alert_with_trace")
                        c["_tool_plan"] = c_plan
                        direct_cands.append(c)
                except Exception as exc:
                    logger.warning("MCP direct match failed for %s: %s", tid, exc)

                # 6. JV consortium complementary matching
                try:
                    j_data, trace = await self.agent._call_tool(
                        session,
                        "discover_jv_consortium_matches",
                        {"tender_id": tid, "current_timestamp": now}
                    )
                    traces.append(trace.model_dump())
                    for jv in j_data.get("consortiums", []):
                        jv["_tender_ref"] = t
                        jv["_tool_plan"] = [
                            "get_tender_requirements",
                            "check_client_coverage (unmet)",
                            "discover_jv_consortium_matches",
                            "dispatch_tender_alert_with_trace",
                        ]
                        jv_list.append(jv)
                except Exception as exc:
                    logger.warning("MCP JV discovery failed for %s: %s", tid, exc)

        logger.info("LangGraph Node 2: Discovered %d single candidates & %d JV consortiums.", len(direct_cands), len(jv_list))
        return {
            "direct_candidates": direct_cands,
            "jv_consortiums": jv_list,
            "tool_traces": traces,
        }

    async def nemotron_cognitive_reasoning_node(self, state: LangGraphAgentState) -> Dict[str, Any]:
        """Node 3: Uses NVIDIA Nemotron 3.5 to synthesize executive bid strategy & decision trees."""
        insights = []
        direct_cands = state.get("direct_candidates", [])
        jv_consortiums = state.get("jv_consortiums", [])
        threshold = state.get("min_score_threshold", 0.50)

        # Synthesize top single candidate with Nemotron if available
        qualified = [c for c in direct_cands if c.get("match_score", 0.0) >= threshold]
        for idx, c in enumerate(qualified[:3]):
            t = c.get("_tender_ref", {})
            c_name = c.get("client_name", c.get("client_id"))
            t_title = t.get("title", t.get("id"))
            score = c.get("match_score", 0.0)
            tool_plan = c.get("_tool_plan", ["get_tender_requirements", "check_client_coverage", "get_department_lineage", "dispatch_tender_alert_with_trace"])
            plan_str = " -> ".join(f"[{i+1}] {step}" for i, step in enumerate(tool_plan))

            reasoning = None
            if self.agent.client_alpha or self.agent.client_beta:
                prompt = (
                    f"You are NVIDIA Nemotron 3.5 AI Agent for an Indian engineering contractor on FalkorDB.\n"
                    f"The agent planned and executed this dynamic tool plan: {plan_str}\n"
                    f"Evaluate this tender match in 3 concise bullet points:\n"
                    f"- Client: {c_name} (Turnover: ₹{c.get('avg_turnover_3yr', 0)/1e7:.2f} Cr)\n"
                    f"- Tender: {t_title} (Expected Turnover: ₹{t.get('expected_turnover_3yr', 0)/1e7:.2f} Cr, Location: {t.get('location', 'India')})\n"
                    f"- Graph Match Score: {round(score*100)}%\n"
                    f"Highlight statutory compliance, capability alignment, and commercial win strategy."
                )
                try:
                    if idx % 2 == 0:
                        llm_text = await self.agent._alpha_call_model_async(
                            prompt=prompt,
                            system_prompt="You are NVIDIA Nemotron 3.5 Agent Alpha, expert Indian Government procurement AI reasoning engine.",
                        )
                    else:
                        llm_text = await self.agent._nemotron_call_model_async(
                            prompt=prompt,
                            system_prompt="You are NVIDIA Nemotron 3.5 Agent Beta, 5-Hop Graph Lookalike & Technical Qualification Engine.",
                        )
                    if llm_text:
                        reasoning = f"TOOL SEQUENCE >> {plan_str}\n\n{llm_text}"
                except Exception as exc:
                    logger.warning("Nemotron LLM call failed, falling back: %s", exc)

            if not reasoning:
                c_syn, _ = self.agent._synthesize_candidate_reasoning(
                    candidate=c,
                    tender_meta=t,
                    tool_plan=tool_plan,
                )
                reasoning = c_syn

            insights.append({
                "type": "SINGLE_BIDDER",
                "client_id": c.get("client_id"),
                "tender_id": t.get("id", t.get("tender_id")),
                "score": score,
                "executive_brief": reasoning,
            })

            # Synthesize lookalike peers discovered through graph hopping with Nemotron
            for peer in c.get("lookalike_peers", []):
                p_id = peer.get("peer_id")
                if not p_id or p_id == c.get("client_id"):
                    continue
                p_name = peer.get("peer_name", p_id)
                shared_caps = peer.get("shared_capabilities", [])
                p_score = round(min(0.95, max(0.60, score * 0.90)), 4)
                peer_plan = [
                    "get_tender_requirements",
                    "check_client_coverage",
                    "find_peer_clients",
                    "dispatch_tender_alert_with_trace",
                ]
                peer_plan_str = " -> ".join(f"[{i+1}] {step}" for i, step in enumerate(peer_plan))

                peer_reasoning = None
                if self.agent.client_alpha or self.agent.client_beta:
                    prompt = (
                        f"You are NVIDIA Nemotron 3.5 AI Agent running on FalkorDB Graph Database.\n"
                        f"The agent executed dynamic template tool plan: {peer_plan_str}\n"
                        f"The AI Agent executed an OpenCypher graph traversal from a top-qualifying benchmark competitor to discover lookalike peer: {p_name} ({p_id}).\n"
                        f"- Tender: {t_title} (Estimated Value: ₹{t.get('tender_amount', 0)/1e7:.2f} Cr, Location: {t.get('location', 'India')})\n"
                        f"- Shared Capabilities in Graph: {', '.join(shared_caps)}\n\n"
                        f"CRITICAL PRIVACY RULE: Do NOT disclose or mention the benchmark competitor's identity or company name.\n"
                        f"Structure your response with:\n"
                        f"1. AI GRAPH HOPPING: Explain the multi-hop path and generated OpenCypher strategy used in FalkorDB.\n"
                        f"2. CONFIDENTIALITY: Note that benchmark competitor details are strictly redacted.\n"
                        f"3. WINNING PLUS POINTS FOR {p_name}: Detail 3-4 specific operational, statutory, and solvency strengths that give {p_name} an edge to win this tender."
                    )
                    try:
                        llm_text = await self.agent._nemotron_call_model_async(
                            prompt=prompt,
                            system_prompt="You are an expert Indian Government procurement AI reasoning engine on Graph DB.",
                        )
                        if llm_text:
                            anchor_ref = f"Benchmark-Ref-{hashlib.sha256(str(c.get('client_id', '')).encode()).hexdigest()[:8].upper()}"
                            peer_reasoning = (
                                f"TOOL SEQUENCE >> {peer_plan_str}\n\n"
                                f"{llm_text}\n\n"
                                f"[System Traversal Reference: {anchor_ref} (Confidential Benchmark - Details Redacted from Client Alert)]"
                            )
                    except Exception as exc:
                        logger.warning("Nemotron LLM call for lookalike peer failed: %s", exc)

                if not peer_reasoning:
                    p_syn, _ = self.agent._synthesize_lookalike_peer_reasoning(
                        candidate=c,
                        peer=peer,
                        tender_meta=t,
                        peer_score=p_score,
                        tool_plan=peer_plan,
                    )
                    peer_reasoning = p_syn

                insights.append({
                    "type": "LOOKALIKE_PEER",
                    "client_id": p_id,
                    "tender_id": t.get("id", t.get("tender_id")),
                    "score": p_score,
                    "executive_brief": peer_reasoning,
                })

        # Synthesize top JV consortium with Nemotron
        for jv in jv_consortiums[:2]:
            t = jv.get("_tender_ref", {})
            lead = jv.get("lead_partner", {})
            partner = jv.get("consortium_partner", {})
            fin = jv.get("combined_financials", {})
            jv_plan = jv.get("_tool_plan", [
                "get_tender_requirements",
                "check_client_coverage (unmet)",
                "discover_jv_consortium_matches",
                "dispatch_tender_alert_with_trace",
            ])
            jv_plan_str = " -> ".join(f"[{i+1}] {step}" for i, step in enumerate(jv_plan))

            jv_insight = None
            if self.agent.client_alpha or self.agent.client_beta:
                prompt = (
                    f"You are NVIDIA Nemotron 3.5 AI Agent. Summarize why this Joint Venture (JV) Consortium is a winning bid:\n"
                    f"- Lead: {lead.get('client_name')} (Turnover: ₹{lead.get('avg_turnover_3yr', 0)/1e7:.2f} Cr)\n"
                    f"- Partner: {partner.get('client_name')} (Turnover: ₹{partner.get('avg_turnover_3yr', 0)/1e7:.2f} Cr)\n"
                    f"- Combined Turnover: ₹{fin.get('combined_turnover', 0)/1e7:.2f} Cr (Required: ₹{fin.get('required_turnover', 0)/1e7:.2f} Cr)\n"
                    f"- Tender: {t.get('title', 'Tender')}\n"
                    f"Provide a 2-sentence executive syndicate recommendation."
                )
                try:
                    llm_text = await self.agent._nemotron_call_model_async(
                        prompt=prompt,
                        system_prompt="You are NVIDIA Nemotron 3.5 Agent Beta, expert Government procurement syndicate strategist.",
                    )
                    if llm_text:
                        jv_insight = (
                            f"JOINT VENTURE (JV) CONSORTIUM MATCH FOR {t.get('id', 'Tender')}:\n"
                            f"TOOL SEQUENCE >> {jv_plan_str}\n"
                            f"- Combined Financials: Combined turnover of ₹{fin.get('combined_turnover', 0)/1e7:.1f} Cr exceeds the ₹{fin.get('required_turnover', 0)/1e7:.1f} Cr threshold.\n"
                            f"{llm_text}"
                        )
                except Exception as exc:
                    logger.warning("Nemotron LLM call for JV failed: %s", exc)

            if not jv_insight:
                lead_syn, _ = self.agent._synthesize_jv_reasoning(jv, t, tool_plan=jv_plan)
                jv_insight = lead_syn

            insights.append({
                "type": "JV_CONSORTIUM",
                "lead_id": lead.get("client_id"),
                "partner_id": partner.get("client_id"),
                "tender_id": t.get("id", t.get("tender_id")),
                "synergy_score": 0.96,
                "executive_brief": jv_insight,
            })

        logger.info("LangGraph Node 3: Synthesized %d cognitive strategy insights.", len(insights))
        return {"executive_strategy_insights": insights}

    
    gemini_cognitive_reasoning_node = nemotron_cognitive_reasoning_node

    async def dispatch_alerts_and_persist_node(self, state: LangGraphAgentState) -> Dict[str, Any]:
        """Node 4: Enforces 2-day cooldown and dispatches alerts via FastMCP."""
        now = state.get("current_timestamp", int(time.time()))
        threshold = state.get("min_score_threshold", 0.50)
        direct_cands = state.get("direct_candidates", [])
        jv_consortiums = state.get("jv_consortiums", [])
        insights_map = {
            (ins.get("client_id") or ins.get("lead_id"), ins.get("tender_id")): ins.get("executive_brief")
            for ins in state.get("executive_strategy_insights", [])
        }

        alerts_dispatched = 0
        alerts_skipped = 0
        decisions = []
        traces = list(state.get("tool_traces", []))

        async with self.agent._connect_session() as session:
            # Dispatch for Single / Lookalike Bidders
            for c in direct_cands:
                score = c.get("match_score", 0.0)
                if score < threshold:
                    continue

                cid = c.get("client_id")
                t = c.get("_tender_ref", {})
                tid = t.get("id") or t.get("tender_id")
                m_type = "LOOKALIKE_PEER" if c.get("lookalike_peers") else "DIRECT"

                reasoning = insights_map.get((cid, tid)) or c.get("graph_path_trace", "Direct qualification.")
                path_summary = c.get("graph_path_trace", f"{cid} -> {tid}")

                try:
                    d_data, trace = await self.agent._call_tool(
                        session,
                        "dispatch_tender_alert_with_trace",
                        {
                            "client_id": cid,
                            "tender_id": tid,
                            "match_score": score,
                            "match_type": m_type,
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                            "current_timestamp": now,
                        }
                    )
                    traces.append(trace.model_dump())

                    if d_data.get("sent") is True:
                        alerts_dispatched += 1
                        decisions.append({
                            "client_id": cid,
                            "tender_id": tid,
                            "match_type": m_type,
                            "match_score": score,
                            "action": "ALERT_SENT",
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                        })
                    else:
                        alerts_skipped += 1
                        decisions.append({
                            "client_id": cid,
                            "tender_id": tid,
                            "match_type": m_type,
                            "match_score": score,
                            "action": "ALERT_SKIPPED",
                            "reason": d_data.get("reason"),
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                        })
                except Exception as exc:
                    logger.warning("Dispatch failed for %s on %s: %s", cid, tid, exc)

                # Lookalike Peer Dispatched Alerts (Graph Hopping)
                for peer in c.get("lookalike_peers", []):
                    p_id = peer.get("peer_id")
                    if not p_id or p_id == cid:
                        continue
                    p_score = round(min(0.95, max(0.60, score * 0.90)), 4)
                    if p_score < threshold:
                        continue
                    p_syn, p_path = self.agent._synthesize_lookalike_peer_reasoning(
                        candidate=c,
                        peer=peer,
                        tender_meta=t,
                        peer_score=p_score
                    )
                    p_reasoning = insights_map.get((p_id, tid)) or p_syn
                    try:
                        p_data, p_trace = await self.agent._call_tool(
                            session,
                            "dispatch_tender_alert_with_trace",
                            {
                                "client_id": p_id,
                                "tender_id": tid,
                                "match_score": p_score,
                                "match_type": "LOOKALIKE_PEER",
                                "reasoning_trace": p_reasoning,
                                "path_summary": p_path,
                                "current_timestamp": now,
                            }
                        )
                        traces.append(p_trace.model_dump())
                        if p_data.get("sent") is True:
                            alerts_dispatched += 1
                            decisions.append({
                                "client_id": p_id,
                                "tender_id": tid,
                                "match_type": "LOOKALIKE_PEER",
                                "match_score": p_score,
                                "action": "ALERT_SENT",
                                "reasoning_trace": p_reasoning,
                                "path_summary": p_path,
                            })
                        else:
                            alerts_skipped += 1
                            decisions.append({
                                "client_id": p_id,
                                "tender_id": tid,
                                "match_type": "LOOKALIKE_PEER",
                                "match_score": p_score,
                                "action": "ALERT_SKIPPED",
                                "reason": p_data.get("reason"),
                                "reasoning_trace": p_reasoning,
                                "path_summary": p_path,
                            })
                    except Exception as exc:
                        logger.warning("Peer dispatch failed for %s on %s: %s", p_id, tid, exc)

            # Dispatch for JV Consortiums (Alert Lead Partner & Consortium Partner)
            for jv in jv_consortiums:
                lead = jv.get("lead_partner", {})
                partner = jv.get("consortium_partner", {})
                lead_id = lead.get("client_id")
                partner_id = partner.get("client_id")
                t = jv.get("_tender_ref", {})
                tid = t.get("id") or t.get("tender_id")
                reasoning = insights_map.get((lead_id, tid)) or jv.get("graph_path_trace", "JV Consortium qualification.")
                path_summary = jv.get("graph_path_trace", f"JV: [{lead_id}] + [{partner_id}] -> {tid}")
                jv_score = float(jv.get("synergy_score", 0.92))
                partner_score = round(max(0.60, jv_score - 0.02), 4)

                # 1. Lead Partner
                try:
                    d_data, trace = await self.agent._call_tool(
                        session,
                        "dispatch_tender_alert_with_trace",
                        {
                            "client_id": lead_id,
                            "tender_id": tid,
                            "match_score": jv_score,
                            "match_type": "JV_CONSORTIUM",
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                            "current_timestamp": now,
                        }
                    )
                    traces.append(trace.model_dump())

                    if d_data.get("sent") is True:
                        alerts_dispatched += 1
                        decisions.append({
                            "client_id": lead_id,
                            "tender_id": tid,
                            "match_type": "JV_CONSORTIUM",
                            "match_score": jv_score,
                            "action": "ALERT_SENT",
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                        })
                    else:
                        alerts_skipped += 1
                        decisions.append({
                            "client_id": lead_id,
                            "tender_id": tid,
                            "match_type": "JV_CONSORTIUM",
                            "match_score": jv_score,
                            "action": "ALERT_SKIPPED",
                            "reason": d_data.get("reason"),
                            "reasoning_trace": reasoning,
                            "path_summary": path_summary,
                        })
                except Exception as exc:
                    logger.warning("JV lead dispatch failed for %s on %s: %s", lead_id, tid, exc)

                # 2. Consortium Partner
                partner_reasoning, partner_path = self.agent._synthesize_jv_partner_reasoning(jv, t)
                try:
                    p_data, p_trace = await self.agent._call_tool(
                        session,
                        "dispatch_tender_alert_with_trace",
                        {
                            "client_id": partner_id,
                            "tender_id": tid,
                            "match_score": partner_score,
                            "match_type": "JV_CONSORTIUM",
                            "reasoning_trace": partner_reasoning,
                            "path_summary": partner_path,
                            "current_timestamp": now,
                        }
                    )
                    traces.append(p_trace.model_dump())

                    if p_data.get("sent") is True:
                        alerts_dispatched += 1
                        decisions.append({
                            "client_id": partner_id,
                            "tender_id": tid,
                            "match_type": "JV_CONSORTIUM",
                            "match_score": partner_score,
                            "action": "ALERT_SENT",
                            "reasoning_trace": partner_reasoning,
                            "path_summary": partner_path,
                        })
                    else:
                        alerts_skipped += 1
                        decisions.append({
                            "client_id": partner_id,
                            "tender_id": tid,
                            "match_type": "JV_CONSORTIUM",
                            "match_score": partner_score,
                            "action": "ALERT_SKIPPED",
                            "reason": p_data.get("reason"),
                            "reasoning_trace": partner_reasoning,
                            "path_summary": partner_path,
                        })
                except Exception as exc:
                    logger.warning("JV partner dispatch failed for %s on %s: %s", partner_id, tid, exc)

        logger.info("LangGraph Node 4: Dispatched %d alerts (%d skipped by 2-day cooldown).", alerts_dispatched, alerts_skipped)
        return {
            "alerts_dispatched": alerts_dispatched,
            "alerts_skipped": alerts_skipped,
            "decisions": decisions,
            "tool_traces": traces,
        }

    def build_graph(self):
        """Builds and compiles the LangGraph StateGraph."""
        builder = StateGraph(LangGraphAgentState)

        builder.add_node("triage_procurement", self.triage_active_procurement_node)
        builder.add_node("graph_matching", self.falkordb_graph_matching_node)
        builder.add_node("cognitive_reasoning", self.nemotron_cognitive_reasoning_node)
        builder.add_node("dispatch_alerts", self.dispatch_alerts_and_persist_node)

        builder.set_entry_point("triage_procurement")
        builder.add_edge("triage_procurement", "graph_matching")
        builder.add_edge("graph_matching", "cognitive_reasoning")
        builder.add_edge("cognitive_reasoning", "dispatch_alerts")
        builder.add_edge("dispatch_alerts", END)

        return builder.compile()

    async def run(
        self,
        current_timestamp: Optional[int] = None,
        min_score_threshold: float = 0.50
    ) -> MatchingLoopResponse:
        """Executes the full LangGraph pipeline and returns a MatchingLoopResponse."""
        now = current_timestamp if current_timestamp is not None else int(time.time())
        initial_state: LangGraphAgentState = {
            "current_timestamp": now,
            "min_score_threshold": min_score_threshold,
            "active_tenders": [],
            "direct_candidates": [],
            "jv_consortiums": [],
            "executive_strategy_insights": [],
            "alerts_dispatched": 0,
            "alerts_skipped": 0,
            "decisions": [],
            "tool_traces": [],
            "errors": [],
        }

        compiled_graph = self.build_graph()
        final_state = await compiled_graph.ainvoke(initial_state)

        decisions_objs = [
            AgentDecisionRecord(
                client_id=d["client_id"],
                tender_id=d["tender_id"],
                match_type=d["match_type"],
                match_score=d["match_score"],
                action=d["action"],
                reason=d.get("reason"),
                reasoning_trace=d["reasoning_trace"],
                path_summary=d["path_summary"],
            )
            for d in final_state.get("decisions", [])
        ]

        tool_traces_objs = [
            ToolCallTrace(**t) for t in final_state.get("tool_traces", [])
        ]

        return MatchingLoopResponse(
            tenders_evaluated=len(final_state.get("active_tenders", [])),
            direct_or_lookalike_matches_found=len(final_state.get("direct_candidates", [])),
            jv_consortiums_found=len(final_state.get("jv_consortiums", [])),
            alerts_dispatched=final_state.get("alerts_dispatched", 0),
            alerts_skipped_cooldown_or_terminal=final_state.get("alerts_skipped", 0),
            decisions=decisions_objs,
            mcp_tool_calls=tool_traces_objs,
            executed_at=now,
        )
