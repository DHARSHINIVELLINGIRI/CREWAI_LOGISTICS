"""
LLM Router Agent
Classifies user intent and routes queries to:
  - Planning Agent (CrewAI) for route/carrier planning
  - Booking Agent (CrewAI) for shipment booking
  - Tracking Agent (MCP Tools) for live tracking, ETA, delay, insights
"""

import os
import re
import json
import datetime
from typing import Literal, Dict, Any

# ── Intent categories ─────────────────────────────────────────────────────────
IntentType = Literal["tracking", "delay", "insight", "booking", "planning", "general"]

# Keyword maps for rule-based classification
_TRACKING_KEYWORDS  = ["where", "track", "location", "status", "shipment", "parcel", "package"]
_DELAY_KEYWORDS     = ["delay", "late", "on time", "arrive", "eta", "predict", "schedule"]
_INSIGHT_KEYWORDS   = ["insight", "tell me", "update", "inform", "progress"]
_BOOKING_KEYWORDS   = ["book", "create", "new shipment", "send", "dispatch", "schedule"]
_PLANNING_KEYWORDS  = ["route", "best carrier", "optimize", "cost", "cheapest", "plan"]


def classify_intent(query: str) -> IntentType:
    """
    Rule-based intent classifier (fast, no LLM required).
    Falls back to 'general' if no strong signal found.
    """
    q = query.lower()
    scores: Dict[str, int] = {
        "tracking": sum(1 for kw in _TRACKING_KEYWORDS if kw in q),
        "delay":    sum(1 for kw in _DELAY_KEYWORDS    if kw in q),
        "insight":  sum(1 for kw in _INSIGHT_KEYWORDS  if kw in q),
        "booking":  sum(1 for kw in _BOOKING_KEYWORDS  if kw in q),
        "planning": sum(1 for kw in _PLANNING_KEYWORDS if kw in q),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    return best


def extract_tracking_id(query: str) -> str | None:
    """Extract SHP-XXXXXX pattern from query text."""
    match = re.search(r"SHP-\d{6}", query, re.IGNORECASE)
    return match.group(0).upper() if match else None


class LLMRouter:
    """
    Routes user queries to the correct agent/service.
    Returns a structured response dict consumed by the Streamlit app.
    """

    def __init__(self, db=None):
        self.db = db
        # Lazy imports to avoid circular deps
        from services.tracking_service import (
            track_shipment,
            predict_shipment_delay,
            generate_ai_insight,
        )
        from services.carrier_analytics import get_analytics
        self._track        = track_shipment
        self._delay        = predict_shipment_delay
        self._insight      = generate_ai_insight
        self._analytics    = get_analytics

    # ── Public entry point ────────────────────────────────────────────────

    def route(self, query: str) -> Dict[str, Any]:
        """
        Main router function.
        Returns dict with keys: intent, agent, response, data, timestamp
        """
        intent = classify_intent(query)
        tracking_id = extract_tracking_id(query)
        timestamp = datetime.datetime.now().isoformat()

        if intent == "tracking" and tracking_id:
            return self._handle_tracking(tracking_id, query, timestamp)

        if intent == "delay" and tracking_id:
            return self._handle_delay(tracking_id, query, timestamp)

        if intent == "insight" and tracking_id:
            return self._handle_insight(tracking_id, query, timestamp)

        if intent in ("booking", "planning"):
            return self._handle_crew_redirect(intent, query, timestamp)

        # Carrier performance query
        if any(c in query.lower() for c in ["carrier", "bluedart", "fedex", "delhivery", "dtdc"]):
            return self._handle_carrier(query, timestamp)

        return self._handle_general(query, timestamp)

    # ── Handlers ──────────────────────────────────────────────────────────

    def _handle_tracking(self, tid: str, query: str, ts: str) -> Dict[str, Any]:
        data = self._track(tid, self.db)
        if data.get("error"):
            msg = data["message"]
        else:
            msg = (
                f"📍 **{tid}** is at **{data['current_city']}**, heading to **{data['next_city']}**.\n"
                f"Status: **{data['status']}** | Speed: {data['speed_kmph']:.0f} km/h\n"
                f"Last updated: {data['last_updated']}"
            )
        return {"intent": "tracking", "agent": "Tracking Agent (MCP)",
                "response": msg, "data": data, "timestamp": ts}

    def _handle_delay(self, tid: str, query: str, ts: str) -> Dict[str, Any]:
        data = self._delay(tid, self.db)
        if data.get("error"):
            msg = data["message"]
        else:
            msg = (
                f"⚠️ Delay prediction for **{tid}**:\n"
                f"Probability: **{data['delay_probability_pct']}** (Risk: {data['risk_level']})\n"
                f"Predicted extra delay: **{data['predicted_delay_minutes']} min**\n"
                f"Reason: {data['reason']}"
            )
        return {"intent": "delay", "agent": "Tracking Agent (MCP)",
                "response": msg, "data": data, "timestamp": ts}

    def _handle_insight(self, tid: str, query: str, ts: str) -> Dict[str, Any]:
        msg = self._insight(tid, self.db)
        return {"intent": "insight", "agent": "Tracking Agent (MCP)",
                "response": msg, "data": {}, "timestamp": ts}

    def _handle_crew_redirect(self, intent: str, query: str, ts: str) -> Dict[str, Any]:
        agent_name = "Planning Agent (CrewAI)" if intent == "planning" else "Booking Agent (CrewAI)"
        msg = (
            f"🔄 Your request has been forwarded to the **{agent_name}**.\n"
            f"Please use the **New Shipment** page to trigger the full agent orchestration."
        )
        return {"intent": intent, "agent": agent_name,
                "response": msg, "data": {}, "timestamp": ts}

    def _handle_carrier(self, query: str, ts: str) -> Dict[str, Any]:
        analytics = self._analytics(self.db)
        rows = analytics.summary_table()
        msg = "📊 **Carrier Performance Summary**\n"
        for r in rows:
            msg += (
                f"• **{r['Carrier']}** — On-time: {r['On-Time Rate (%)']}% | "
                f"Avg Delay: {r['Avg Delay (min)']} min | Score: {r['Reliability Score']:.2f}\n"
            )
        return {"intent": "analytics", "agent": "Analytics Service",
                "response": msg, "data": rows, "timestamp": ts}

    def _handle_general(self, query: str, ts: str) -> Dict[str, Any]:
        msg = (
            "🤖 I'm your **Logistics AI Assistant**. I can help you with:\n"
            "• **Track** a shipment (e.g. 'Where is SHP-123456?')\n"
            "• **Delay prediction** (e.g. 'Will SHP-123456 be delayed?')\n"
            "• **Carrier analytics** (e.g. 'Show BlueDart performance')\n"
            "• **Booking** — use the New Shipment page\n\n"
            "Please include a valid tracking ID (SHP-XXXXXX) for shipment queries."
        )
        return {"intent": "general", "agent": "LLM Router",
                "response": msg, "data": {}, "timestamp": ts}
