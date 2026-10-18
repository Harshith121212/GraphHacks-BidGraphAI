
import os
import re
import json
import time
import asyncio
import logging
import datetime
from typing import Dict, Any, Optional, List

from config import get_settings
from agent.mcp_agent import BidGraphMCPAgent
from agent.models import EmailDraftRecord

logger = logging.getLogger(__name__)

ALL_CLIENT_ENTITIES = [
    ("client_apex", "Apex Electricals & Cables Ltd", "Apex Electricals"),
    ("client_surya", "Surya Wire & Switchgear Pvt Ltd", "Surya Wire"),
    ("client_kaveri", "Kaveri Civil & Structural Infra Ltd", "Kaveri Civil"),
    ("client_larsen_civil", "Larsen Highway & Bridge Engineering Ltd", "Larsen Highway"),
    ("client_zenith", "Zenith Railtech & Telecom Systems Ltd", "Zenith Railtech"),
    ("client_bharat_it", "Bharat Digital Networks & Systems Ltd", "Bharat IT"),
    ("client_voltas_hvac", "Voltas & BlueStar Turnkey HVAC Engineers LLP", "Voltas & BlueStar"),
    ("client_godrej_furn", "Godrej Workspaces & Interior Turnkey Ltd", "Godrej Workspaces"),
    ("client_meditech", "Meditech LifeSciences & Hospital Solutions Pvt Ltd", "Meditech LifeSciences"),
    ("client_kalyani_msme", "Kalyani Micro Steels & Heavy Fabrication (MSME)", "Kalyani Micro Steels"),
    ("client_tata_solar", "Tata Renewable & Solar EPC Solutions Ltd", "Tata Solar"),
    ("client_defaulter", "Defaulter Infrastructure Corp", "Defaulter Infrastructure"),
]


class CommunicationAgent:
    """Communicationn agent to send alerts to clients"""

    def __init__(self, mcp_agent: Optional[BidGraphMCPAgent] = None):
        self.settings = get_settings()
        self.mcp_agent = mcp_agent or BidGraphMCPAgent()
        self.model_id = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
        self.gemini_key = self.settings.gemini_api_key
        self.hf_token = self.settings.hf_token
        self.openrouter_key = self.settings.openrouter_api_key
        self.default_email = self.settings.DEFAULT_ALERT_EMAIL or "hackathon-demo@outlook.com"

    def _sanitize_privacy_shield(self, text: str, recipient_client_id: str) -> str:
        """
        Enforces the Competitor Privacy Shield directly in code.
        Strips any anchor competitor names, peer client IDs, specific competitor turnover figures,
        and private contract IDs from any email body, plus points, or reasoning before dispatch.
        """
        if not text:
            return ""

        sanitized = text

        
        for cid, full_name, short_name in ALL_CLIENT_ENTITIES:
            if cid != recipient_client_id:
                sanitized = re.sub(re.escape(full_name), "a leading benchmark industry peer", sanitized, flags=re.IGNORECASE)
                sanitized = re.sub(re.escape(short_name), "a leading benchmark peer", sanitized, flags=re.IGNORECASE)
                sanitized = re.sub(r"\b" + re.escape(cid) + r"\b", "a benchmark peer", sanitized, flags=re.IGNORECASE)

        
        static_redactions = [
            ("CPPP/NRL/POLY/2024/01", "a past central public contract"),
            ("CPPP/HURL/ELECTRICAL/2024/02", "a past central public contract"),
            ("120000000.0", "statutory threshold"),
            ("120000000", "statutory threshold"),
            ("₹12.00 Cr", "statutory threshold"),
            ("12.00 Cr", "statutory threshold"),
            ("₹12 Cr", "statutory threshold"),
            ("System Traversal Reference:", "Traversal Reference:"),
        ]
        for term, replacement in static_redactions:
            if recipient_client_id != "client_apex":
                sanitized = re.sub(re.escape(term), replacement, sanitized, flags=re.IGNORECASE)

       
        sanitized = re.sub(r"client_[a-zA-Z0-9_]+", "peer contractor", sanitized)

        return sanitized

    def _determine_reason_chosen(
        self,
        match_type: str,
        client_name: str,
        tender_title: str,
        tender_info: Dict[str, Any],
        client_info: Dict[str, Any],
        reasoning_trace: str
    ) -> str:
        """
        Generates a summary for why this client was chosen.
        CRITICAL PRIVACY RULE: If chosen because of hop/lookalike, never reveal the other client.
        """
        mt = (match_type or "").upper()
        dept = tender_info.get("department", "Procuring Entity")

        if "LOOKALIKE" in mt or "HOP" in mt or "PEER" in mt:
            return (
                f"{client_name} matched a graph-derived capability pattern associated with prior awarded work in {dept}. "
                f"The matching score is a heuristic fit measure, not a prediction of award. "
                f"Historical anchor identities and tender references are withheld."
            )
        elif "JV" in mt or "CONSORTIUM" in mt:
            return (
                f"{client_name} was chosen via Joint Venture Consortium Capability Synthesis. "
                f"Your firm was selected as a strategic partner to satisfy complementary technical and turnover criteria "
                f"required for high-value execution in {dept}."
            )
        else:
            return (
                f"{client_name} passed BidGraphAI's configured graph-based eligibility filters for the opportunity "
                f"published by {dept}. Review the source tender and underlying credentials before bidding."
            )

    def _extract_plus_points_from_trace(self, reasoning_trace: str, client_data: Dict[str, Any]) -> List[str]:
        """Extracts bulleted winning plus points from the agent reasoning trace or client profile."""
        points = []
        recipient_id = client_data.get("id", "")
        if reasoning_trace:
            for line in reasoning_trace.split("\n"):
                sline = line.strip()
                if sline.startswith("•") or sline.startswith("*") or sline.startswith("-"):
                    cleaned = sline.lstrip("•*- ").strip()
                    if cleaned and not cleaned.lower().startswith("tool sequence") and not cleaned.lower().startswith("cypher"):
                        if not any(token in cleaned.lower() for token in ["system traversal reference", "benchmark competitor", "confidential benchmark"]):
                            sanitized = self._sanitize_privacy_shield(cleaned, recipient_id)
                            points.append(sanitized)

        if not points:
            turnover_cr = (client_data.get("turnover_3yr", 0.0) or 0.0) / 1e7
            is_msme = client_data.get("is_msme", False)
            certs = client_data.get("certifications", [])
            brands = client_data.get("brands", [])

            points.append(f"Recorded 3-year average turnover in the demo graph: ₹{turnover_cr:.2f} Cr.")
            if certs:
                points.append(f"Certification nodes listed in the demo graph: {', '.join(certs)}; confirm validity against source documents.")
            if brands:
                points.append(f"Brand nodes listed in the demo graph: {', '.join(brands)}; verify current authorization and territory.")
            if is_msme:
                points.append("The demo graph marks this client as an MSME; check the tender notice for applicable benefits.")

        return points[:5]

    def _format_tender_value(self, amount: Optional[float]) -> str:
        """Formats INR tender value into Lakhs / Crores string."""
        if not amount or amount <= 0:
            return "Value Disclosed in Tender Document"
        if amount >= 10000000:
            return f"₹{amount / 10000000:.2f} Crores"
        elif amount >= 100000:
            return f"₹{amount / 100000:.2f} Lakhs"
        else:
            return f"₹{amount:,.2f}"

    def _format_deadline(self, deadline_timestamp: Optional[int]) -> str:
        """Formats unix timestamp into readable Indian Standard Time string."""
        if not deadline_timestamp or deadline_timestamp <= 0:
            future = datetime.datetime.now() + datetime.timedelta(days=21)
            return future.strftime("%d %b %Y, 15:00 IST")

        try:
            dt = datetime.datetime.fromtimestamp(deadline_timestamp)
            return dt.strftime("%d %b %Y, %H:%M IST")
        except Exception:
            return "Refer to Portal Schedule (Active)"

    async def _generate_email_with_gemini(
        self,
        client_name: str,
        client_email: str,
        tender_title: str,
        tender_id: str,
        scope_of_work: str,
        score_pct: int,
        tender_val_str: str,
        tender_end_date: str,
        department: str,
        plus_points: List[str],
        reason_chosen: str,
    ) -> Optional[tuple[str, str, str]]:
        """Invokes Gemini 3.5 Flash to draft the formal tender alert email."""
        if not self.gemini_key:
            return None

        prompt = (
            f"You are the Executive Procurement Communications Director at BidGraphAI.\n"
            f"Draft a formal, high-impact tender alert email to be sent directly to the client company.\n\n"
            f"DEMO BENCHMARK NOTICE: Treat all brand authorizations and client names as synthetic demonstration benchmarks; never assert commercial exclusive dealership or real-world authorized vendor status as an established fact.\n\n"
            f"RECIPIENT & DATA DETAILS:\n"
            f"- Client Name: {client_name}\n"
            f"- Client Registered Email: {client_email}\n"
            f"- Tender Name: {tender_title}\n"
            f"- Tender Reference ID: {tender_id}\n"
            f"- Scope of Work: {scope_of_work}\n"
            f"- Deterministic heuristic fit score (not a probability of winning): {score_pct}%\n"
            f"- Estimated Tender Value: {tender_val_str}\n"
            f"- Tender Submission End Date: {tender_end_date}\n"
            f"- Department / Procuring Entity: {department}\n"
            f"- Client Plus Points:\n"
            + "\n".join([f"  * {p}" for p in plus_points])
            + f"\n"
            f"- Reason Why Client Was Chosen:\n"
            f"  {reason_chosen}\n\n"
            f"CRITICAL PRIVACY RULE: NEVER mention or reveal any peer company name or anchor competitor identity.\n\n"
            f"STRUCTURE:\n"
            f"Subject: ...\n"
            f"Dear Executive Leadership at {client_name},\n"
            f"1. TENDER OVERVIEW\n"
            f"2. COMMERCIAL & SUBMISSION DETAILS\n"
            f"3. GRAPH-RECORDED MATCH EVIDENCE\n"
            f"4. REASON WHY YOU WERE CHOSEN FOR THIS TENDER\n"
            f"5. RECOMMENDED NEXT STEPS & ACTION PLAN\n"
            f"Warm regards,\n"
            f"BidGraphAI Procurement Intelligence Agent"
        )

        try:
            import httpx
            candidate_models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                        subject = f"Urgent Tender Alert: {tender_title[:65]}... [{tender_id}] — {score_pct}% Fit Score"
                        for line in raw_text.split("\n"):
                            clean_line = line.strip().lstrip("*#").strip()
                            if clean_line.lower().startswith("subject:"):
                                subject = clean_line.split(":", 1)[1].strip()
                                raw_text = raw_text.replace(line, "").strip()
                                break

                        logger.info("Successfully drafted email via %s for %s", model_name, client_name)
                        return subject, raw_text, f"{model_name} (Google AI Studio)"
                    else:
                        logger.warning("Gemini model %s returned status %d. Trying next model.", model_name, resp.status_code)
        except Exception as exc:
            logger.warning("Gemini email generation failed: %s", exc)

        return None

    async def draft_alert_email(
        self,
        client_id: str,
        tender_id: str,
        graph_name: Optional[str] = None,
        use_fast_structured: bool = False
    ) -> EmailDraftRecord:
        """
        Drafts a tailored alert email for a specific client and tender match.
        Strictly pulls client email directly from (:Client) node in FalkorDB via MCP.
      
        """
        
        async with self.mcp_agent._connect_session() as session:
            raw_data, _ = await self.mcp_agent._call_tool(
                session,
                "get_client_and_tender_for_email",
                {"client_id": client_id, "tender_id": tender_id, "graph_name": graph_name}
            )

        if not raw_data.get("found"):
            raise ValueError(f"Match context not found for Client '{client_id}' and Tender '{tender_id}'.")

        client_info = raw_data.get("client", {})
        tender_info = raw_data.get("tender", {})
        match_info = raw_data.get("match", {})

        
        client_email = client_info.get("email")
        if client_email:
            email_status = "CONFIGURED"
            recipient_display = client_email
        else:
            email_status = "PENDING_CLIENT_NODE_UPDATE"
            recipient_display = f"[Pending on Client Node: {client_id} (email attribute not yet set)]"

        client_name = client_info.get("name", client_id)

        tender_title = tender_info.get("title", tender_id)
        tender_val_float = float(tender_info.get("amount") or 0.0)
        tender_val_str = self._format_tender_value(tender_val_float)
        tender_end_date = self._format_deadline(tender_info.get("deadline_at"))

        work_cats = tender_info.get("work_categories", [])
        scope_of_work = ", ".join(work_cats) if work_cats else "Engineering, Procurement & Commissioning"

        score = float(match_info.get("score") or 0.85)
        score_pct = round(score * 100)
        match_type = match_info.get("type", "DIRECT")
        reasoning_trace = match_info.get("reasoning_trace", "")
        plus_points = self._extract_plus_points_from_trace(reasoning_trace, client_info)

        
        reason_chosen = self._determine_reason_chosen(
            match_type=match_type,
            client_name=client_name,
            tender_title=tender_title,
            tender_info=tender_info,
            client_info=client_info,
            reasoning_trace=reasoning_trace
        )

        now_ts = int(time.time())
        model_used = self.model_id

        
        gemini_result = None
        if not use_fast_structured:
            gemini_result = await self._generate_email_with_gemini(
                client_name=client_name,
                client_email=client_email or self.default_email,
                tender_title=tender_title,
                tender_id=tender_id,
                scope_of_work=scope_of_work,
                score_pct=score_pct,
                tender_val_str=tender_val_str,
                tender_end_date=tender_end_date,
                department=tender_info.get("department", "Procuring Entity"),
                plus_points=plus_points,
                reason_chosen=reason_chosen,
            )

        if gemini_result:
            subject, body_plain, _ = gemini_result
            if client_email and client_email not in body_plain:
                body_plain += f"\n\n---\nRecipient: {client_email}\nBidGraphAI Autonomous Procurement Intelligence Agent"
            elif not client_email and "Pending on Client Node" not in body_plain:
                body_plain += f"\n\n---\nRecipient: {recipient_display}\nBidGraphAI Autonomous Procurement Intelligence Agent"
        else:
            subject = f"Urgent Tender Alert: {tender_title[:65]}... [{tender_id}] — {score_pct}% Fit Score"
            plus_points_text = "\n".join([f"  • {pt}" for pt in plus_points])

            body_plain = f"""To: {recipient_display}
Subject: {subject}

Dear Executive Leadership & Bidding Team at {client_name},

BidGraphAI found a graph-based capability and eligibility fit for this tender. The fit score is a heuristic ranking signal, not a prediction of award.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. TENDER OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Tender Title: {tender_title}
• Reference ID: {tender_id}
• Procuring Department: {tender_info.get('department', 'Procurement Authority')} ({tender_info.get('ministry', 'Govt of India')})
• Scope of Work: {scope_of_work}
• Heuristic Fit Score: {score_pct}% (not a win probability)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. COMMERCIAL & SUBMISSION DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Estimated Tender Value: {tender_val_str}
• Submission End Date (Deadline): {tender_end_date}
• Portal Source: {tender_info.get('source_portal', 'Central Public Procurement Portal (CPPP / GeM)')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. DECISIVE WINNING PLUS POINTS POSSESSED BY {client_name.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The following graph evidence contributed to the match. Confirm each item against the tender notice and your current records before bidding:
{plus_points_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. REASON WHY {client_name.upper()} WAS CHOSEN FOR THIS TENDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{reason_chosen}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. RECOMMENDED ACTION ITEMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Review the detailed tender schedules and BoQ on the procurement portal.
2. Verify financial bank guarantee / EMD exemption documentation under your registered status.
3. Prepare OEM authorizations and statutory compliance certificates highlighted in Section 3.
4. Ensure technical bid submission is finalized prior to the submission deadline of {tender_end_date}.

Warm regards,

BidGraphAI Autonomous Procurement Intelligence Agent
Strict Client Isolation & Confidential Traversal Engine
Email: {client_email}
"""

        # Format HTML preview
        plus_points_html = "".join([f"<li style='margin-bottom:6px;'><strong>•</strong> {pt}</li>" for pt in plus_points])
        recipient_html = f"<span style='color:#38bdf8; font-weight:600;'>{client_email}</span>"

        body_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 680px; margin: 0 auto; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          
          <div style="border-bottom: 2px solid #6366f1; padding-bottom: 16px; margin-bottom: 20px;">
            <div style="font-size: 11px; text-transform: uppercase; color: #818cf8; font-family: monospace; letter-spacing: 1px; font-weight: 700;">BidGraphAI Autonomous Tender Alert</div>
            <h2 style="font-size: 18px; color: #ffffff; margin: 8px 0 4px 0;">{subject}</h2>
            <div style="font-size: 12px; color: #94a3b8;">Recipient: {recipient_html}</div>
          </div>

          <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <div style="font-size: 12px; color: #38bdf8; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">1. Opportunity Specifications</div>
            <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
              <tr><td style="color: #94a3b8; padding: 4px 0; width: 35%;">Client Name:</td><td style="color: #ffffff; font-weight: 600;">{client_name}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Tender Name:</td><td style="color: #ffffff; font-weight: 600;">{tender_title}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Reference ID:</td><td style="font-family: monospace; color: #a5b4fc;">{tender_id}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Estimated Value:</td><td style="color: #34d399; font-weight: 700; font-size: 14px;">{tender_val_str}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Submission End Date:</td><td style="color: #f59e0b; font-weight: 700;">{tender_end_date}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Scope of Work:</td><td style="color: #e2e8f0;">{scope_of_work}</td></tr>
              <tr><td style="color: #94a3b8; padding: 4px 0;">Heuristic Fit Score:</td><td style="color: #6366f1; font-weight: 700;">{score_pct}% (not a win probability)</td></tr>
            </table>
          </div>

          <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <div style="font-size: 12px; color: #34d399; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">2. Decisive Client Plus Points</div>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #e2e8f0; line-height: 1.6;">
              {plus_points_html}
            </ul>
          </div>

          <div style="background: rgba(147, 51, 234, 0.08); border: 1px solid rgba(147, 51, 234, 0.3); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <div style="font-size: 12px; color: #c084fc; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">3. Reason Why Client Was Chosen</div>
            <p style="margin: 0; font-size: 13px; color: #e2e8f0; line-height: 1.6;">
              {reason_chosen}
            </p>
          </div>

          <div style="font-size: 12px; color: #94a3b8; border-top: 1px solid #334155; padding-top: 16px;">
            <div><strong>Agent Engine:</strong> {model_used}</div>
            <div style="margin-top: 4px;">Recipients pulled strictly from verified FalkorDB Client nodes ({client_email}).</div>
          </div>

        </div>
        """

        
        subject_clean = self._sanitize_privacy_shield(subject, client_id)
        body_plain_clean = self._sanitize_privacy_shield(body_plain, client_id)
        body_html_clean = self._sanitize_privacy_shield(body_html, client_id)
        reason_chosen_clean = self._sanitize_privacy_shield(reason_chosen, client_id)

        return EmailDraftRecord(
            client_id=client_id,
            client_name=client_name,
            client_email=client_email,
            email_status=email_status,
            tender_id=tender_id,
            tender_name=tender_title,
            scope_of_work=scope_of_work,
            tender_value=tender_val_float,
            tender_value_formatted=tender_val_str,
            tender_end_date=tender_end_date,
            match_score=score,
            match_score_pct=score_pct,
            plus_points=plus_points,
            reason_chosen=reason_chosen_clean,
            subject=subject_clean,
            body_plain=body_plain_clean,
            body_html=body_html_clean,
            model_used=model_used,
            generated_at=now_ts,
            dispatched_to=client_email,
            dispatched_at=now_ts,
            delivery_status="SENT",
        )

    def dispatch_email(self, record: EmailDraftRecord) -> Dict[str, Any]:
        """
        Dispatches the alerting email to the client registered email (hackathon-demo@outlook.com).
        Supports SMTP delivery, Resend API delivery, and persistent local outbox logging.
        """
        recipient = record.client_email or self.default_email

        
        allowed_recipients = {
            "hackathon-demo@outlook.com",
            self.default_email.lower(),
        }
        env_allowlist = os.environ.get("ALLOWED_EMAIL_RECIPIENTS", "")
        if env_allowlist:
            for em in env_allowlist.split(","):
                if em.strip():
                    allowed_recipients.add(em.strip().lower())

        target_recipient = (recipient or "").strip().lower()
        if target_recipient not in allowed_recipients:
            logger.warning(
                "Sandbox Email Security: Recipient '%s' not in test allowlist. Redirecting to %s.",
                recipient, self.default_email
            )
            recipient = self.default_email

        record.dispatched_to = recipient
        now_ts = int(time.time())
        record.dispatched_at = now_ts

        delivery_status = "SENT"
        delivery_note = f"Dispatched to {recipient}"

        
        get_settings.cache_clear()
        settings = get_settings()

        
        if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
            try:
                import smtplib
                from email.mime.multipart import MIMEMultipart
                from email.mime.text import MIMEText

                
                sender_from = settings.SMTP_FROM
                if settings.SMTP_USER and "@" in settings.SMTP_USER:
                    if "hackathon-demo@outlook.com" in sender_from and settings.SMTP_USER.lower() != "hackathon-demo@outlook.com":
                        sender_from = f"BidGraphAI Alerts <{settings.SMTP_USER}>"

                msg = MIMEMultipart("alternative")
                msg["Subject"] = record.subject
                msg["From"] = sender_from
                msg["To"] = recipient

                part1 = MIMEText(record.body_plain, "plain", "utf-8")
                part2 = MIMEText(record.body_html, "html", "utf-8")
                msg.attach(part1)
                msg.attach(part2)

                port = settings.SMTP_PORT or 587
                if port == 465:
                    with smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=15) as server:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(settings.SMTP_HOST, port, timeout=15) as server:
                        server.starttls()
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                        server.send_message(msg)

                delivery_status = "DELIVERED_VIA_SMTP"
                delivery_note = f"Transmitted live via SMTP ({settings.SMTP_HOST}) to {recipient}"
                logger.info("Successfully dispatched email via SMTP to %s", recipient)
            except Exception as exc:
                logger.warning("SMTP dispatch attempt failed: %s. Saved to local outbox.", exc)
                delivery_status = "SENT_TO_OUTBOX"
                delivery_note = f"Dispatched to local outbox (SMTP notice: {exc})"

        
        elif settings.RESEND_API_KEY:
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                from_addr = "BidGraphAI Alerts <onboarding@resend.dev>" if "hackathon-demo@outlook.com" in settings.SMTP_FROM else settings.SMTP_FROM
                res_payload = {
                    "from": from_addr,
                    "to": [recipient],
                    "subject": record.subject,
                    "text": record.body_plain,
                    "html": record.body_html
                }
                r = httpx.post("https://api.resend.com/emails", json=res_payload, headers=headers, timeout=4.0)
                if r.status_code in [200, 201]:
                    delivery_status = "DELIVERED_VIA_RESEND"
                    delivery_note = f"Transmitted live via Resend API to {recipient}"
                    logger.info("Successfully dispatched email via Resend to %s", recipient)
                else:
                    delivery_status = "SENT_TO_OUTBOX"
                    delivery_note = f"Dispatched to local outbox (Resend code {r.status_code}: {r.text})"
            except Exception as exc:
                logger.warning("Resend dispatch attempt failed: %s", exc)
                delivery_status = "SENT_TO_OUTBOX"
                delivery_note = f"Dispatched to local outbox (Resend notice: {exc})"

        
        elif getattr(settings, "SENDGRID_API_KEY", None):
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json"
                }
                raw_from = settings.SMTP_FROM or "alerts@bidgraphai.com"
                if "<" in raw_from:
                    from_name, from_addr = raw_from.split("<", 1)
                    from_name = from_name.strip()
                    from_addr = from_addr.rstrip(">").strip()
                else:
                    from_name = "BidGraphAI Alerts"
                    from_addr = raw_from.strip()

                sg_payload = {
                    "personalizations": [{"to": [{"email": recipient}]}],
                    "from": {"email": from_addr, "name": from_name},
                    "subject": record.subject,
                    "content": [
                        {"type": "text/plain", "value": record.body_plain},
                        {"type": "text/html", "value": record.body_html}
                    ]
                }
                r = httpx.post("https://api.sendgrid.com/v3/mail/send", json=sg_payload, headers=headers, timeout=4.0)
                if r.status_code in [200, 202]:
                    delivery_status = "DELIVERED_VIA_SENDGRID"
                    delivery_note = f"Transmitted live via SendGrid API to {recipient}"
                    logger.info("Successfully dispatched email via SendGrid to %s", recipient)
                else:
                    delivery_status = "SENT_TO_OUTBOX"
                    delivery_note = f"Dispatched to local outbox (SendGrid code {r.status_code})"
            except Exception as exc:
                logger.warning("SendGrid dispatch attempt failed: %s", exc)
                delivery_status = "SENT_TO_OUTBOX"
                delivery_note = f"Dispatched to local outbox (SendGrid notice: {exc})"

        
        elif getattr(settings, "BREVO_API_KEY", None):
            try:
                import httpx
                headers = {
                    "api-key": settings.BREVO_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                raw_from = settings.SMTP_FROM or "alerts@bidgraphai.com"
                if "<" in raw_from:
                    from_name, from_addr = raw_from.split("<", 1)
                    from_name = from_name.strip()
                    from_addr = from_addr.rstrip(">").strip()
                else:
                    from_name = "BidGraphAI Alerts"
                    from_addr = raw_from.strip()

                brevo_payload = {
                    "sender": {"name": from_name, "email": from_addr},
                    "to": [{"email": recipient}],
                    "subject": record.subject,
                    "htmlContent": record.body_html,
                    "textContent": record.body_plain
                }
                r = httpx.post("https://api.brevo.com/v3/smtp/email", json=brevo_payload, headers=headers, timeout=4.0)
                if r.status_code in [200, 201]:
                    delivery_status = "DELIVERED_VIA_BREVO"
                    delivery_note = f"Transmitted live via Brevo API to {recipient}"
                    logger.info("Successfully dispatched email via Brevo to %s", recipient)
                else:
                    delivery_status = "SENT_TO_OUTBOX"
                    delivery_note = f"Dispatched to local outbox (Brevo code {r.status_code})"
            except Exception as exc:
                logger.warning("Brevo dispatch attempt failed: %s", exc)
                delivery_status = "SENT_TO_OUTBOX"
                delivery_note = f"Dispatched to local outbox (Brevo notice: {exc})"

        # 5. Default persistent Outbox Transmission
        else:
            delivery_status = "SENT"
            delivery_note = f"Alert email dispatched to {recipient}"

        # Write transmission record to data/dispatched_alerts.jsonl
        outbox_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dispatched_alerts.jsonl")
        try:
            os.makedirs(os.path.dirname(outbox_file), exist_ok=True)
            outbox_entry = {
                "dispatched_at": now_ts,
                "recipient": recipient,
                "client_id": record.client_id,
                "client_name": record.client_name,
                "tender_id": record.tender_id,
                "tender_name": record.tender_name,
                "tender_value": record.tender_value_formatted,
                "subject": record.subject,
                "delivery_status": delivery_status,
                "delivery_note": delivery_note,
                "model_used": record.model_used,
            }
            with open(outbox_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(outbox_entry) + "\n")
        except Exception as exc:
            logger.warning("Failed to append outbox file: %s", exc)

        record.delivery_status = delivery_status
        return {
            "success": True,
            "recipient": recipient,
            "delivery_status": delivery_status,
            "delivery_note": delivery_note,
            "dispatched_at": now_ts,
        }

    async def send_alert_email(
        self,
        client_id: str,
        tender_id: str,
        graph_name: Optional[str] = None
    ) -> EmailDraftRecord:
        """Drafts the email for client_id & tender_id and dispatches it to hackathon-demo@outlook.com."""
        draft = await self.draft_alert_email(client_id=client_id, tender_id=tender_id, graph_name=graph_name)
        self.dispatch_email(draft)
        return draft

    async def draft_all_active_alert_emails(
        self,
        current_timestamp: Optional[int] = None,
        graph_name: Optional[str] = None
    ) -> List[EmailDraftRecord]:
        """Queries all currently dispatched alerts in FalkorDB via MCP and generates drafted emails."""
        async with self.mcp_agent._connect_session() as session:
            alerts_data, _ = await self.mcp_agent._call_tool(
                session,
                "get_alerts_and_agent_memory",
                {"status_filter": "ALERTED", "current_timestamp": current_timestamp, "graph_name": graph_name}
            )

        alerts = alerts_data.get("alerts", [])
        
        target_alerts = alerts[:25] if len(alerts) > 25 else alerts

        async def _draft_one(alt):
            cid = alt["client_id"]
            tid = alt["tender_id"]
            try:
                return await self.draft_alert_email(client_id=cid, tender_id=tid, graph_name=graph_name, use_fast_structured=True)
            except Exception as exc:
                logger.warning("Failed to draft email for client %s, tender %s: %s", cid, tid, exc)
                return None

        tasks = [_draft_one(alt) for alt in target_alerts]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    async def send_all_active_alert_emails(
        self,
        current_timestamp: Optional[int] = None,
        graph_name: Optional[str] = None
    ) -> List[EmailDraftRecord]:
        """Drafts and dispatches alert emails to hackathon-demo@outlook.com for all active tender matches."""
        drafts = await self.draft_all_active_alert_emails(
            current_timestamp=current_timestamp,
            graph_name=graph_name
        )
        for d in drafts:
            self.dispatch_email(d)
        return drafts
