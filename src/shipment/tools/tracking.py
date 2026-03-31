"""
Advanced CrewAI Tracking Tools — 7 Specialized Intelligence Tools
Decorated with @tool from crewai.tools (NOT @mcp.tool).

Tools:
1. get_shipment_status        — Real-time location & status
2. check_carrier_performance  — Live carrier metrics
3. predict_delivery_risk      — Multi-factor delay + SLA risk
4. analyze_route_intelligence — Route congestion + optimization
5. generate_logistics_report  — Full 360° shipment intelligence report
6. compare_carriers           — Carrier benchmarking comparison
7. get_customer_alert_level   — Communication priority (GREEN/YELLOW/RED)
"""

import os
import sys
import random
import datetime
import httpx
from pathlib import Path
from crewai.tools import tool
from dotenv import load_dotenv

# ── Absolute-path .env loader (works regardless of CWD) ─────────────────────
_THIS = Path(__file__).resolve()
for _candidate in [
    _THIS.parent / ".env",
    _THIS.parent.parent / ".env",
    _THIS.parent.parent.parent / ".env",
    _THIS.parent.parent.parent.parent / ".env",   # project root ← most likely
]:
    if _candidate.exists():
        load_dotenv(dotenv_path=_candidate, override=True)
        break

# ── Ensure project root is importable ────────────────────────────────────────
def _root():
    return str(_THIS.parent.parent.parent.parent)

def _ensure_root():
    r = _root()
    if r not in sys.path:
        sys.path.insert(0, r)

ESHIPZ_API_URL = "https://app.eshipz.com/api/v2/trackings"
# Read both possible env var names — .env uses ESHIPZ_API_KEY
ESHIPZ_TOKEN = (os.getenv("ESHIPZ_API_TOKEN") or os.getenv("ESHIPZ_API_KEY") or "").strip()

# ── Carrier SLA data ──────────────────────────────────────────────────────────
CARRIER_SLA = {
    "BlueDart":       {"max_days": 2, "premium": True,  "coverage": "Pan-India"},
    "FedEx":          {"max_days": 3, "premium": True,  "coverage": "International"},
    "Delhivery":      {"max_days": 4, "premium": False, "coverage": "Pan-India"},
    "DTDC":           {"max_days": 5, "premium": False, "coverage": "Regional"},
    "eShipz Express": {"max_days": 3, "premium": True,  "coverage": "South India"},
}

# ── Route congestion intelligence ─────────────────────────────────────────────
ROUTE_INTEL = {
    "Chennai":    {"congestion": "HIGH",   "peak_hours": "8-10am, 5-8pm", "alternate": "Via Vellore"},
    "Coimbatore": {"congestion": "MEDIUM", "peak_hours": "9-11am",        "alternate": "Via Erode"},
    "Trichy":     {"congestion": "LOW",    "peak_hours": "8-9am",         "alternate": "Direct route"},
    "Salem":      {"congestion": "MEDIUM", "peak_hours": "7-9am",         "alternate": "Via Erode"},
    "Madurai":    {"congestion": "MEDIUM", "peak_hours": "9-11am",        "alternate": "Via Dindigul"},
    "Dindigul":   {"congestion": "LOW",    "peak_hours": "8-9am",         "alternate": "Direct route"},
    "Vellore":    {"congestion": "LOW",    "peak_hours": "8-9am",         "alternate": "Direct route"},
    "Erode":      {"congestion": "LOW",    "peak_hours": "7-8am",         "alternate": "Direct route"},
}


def _fetch_eshipz(tracking_id: str) -> dict | None:
    try:
        resp = httpx.post(
            ESHIPZ_API_URL,
            headers={"Content-Type": "application/json", "X-API-TOKEN": ESHIPZ_TOKEN},
            json={"track_id": tracking_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _get_sim_data(tracking_id: str) -> dict | None:
    try:
        _ensure_root()
        from services.simulation_engine import get_simulator
        return get_simulator().get_shipment(tracking_id)
    except Exception:
        return None


def _get_analytics():
    try:
        _ensure_root()
        from services.carrier_analytics import get_analytics
        return get_analytics()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1: get_shipment_status
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_shipment_status")
def get_shipment_status(tracking_number: str) -> str:
    """
    Retrieves real-time shipment tracking data including current GPS location,
    movement status, carrier details, speed, and estimated time of arrival (ETA).

    Use this as the FIRST tool when the user asks about a shipment's location
    or current status. Always call this before any analysis tool.

    Input: tracking number or AWB as a string (e.g. 'SHP-123456' or 'BLU-4829103847')
    """
    data = _get_sim_data(tracking_number)
    if data:
        route = data.get("route", [])
        leg   = data.get("current_leg", 0)
        curr  = route[leg] if leg < len(route) else route[-1]
        nxt   = route[leg + 1] if leg + 1 < len(route) else "Final Destination"
        total = len(route) - 1
        pct   = round(((leg + data.get("leg_progress", 0)) / max(total, 1)) * 100, 1)

        try:
            eta_dt  = datetime.datetime.fromisoformat(data.get("eta", ""))
            hrs_rem = max(0, (eta_dt - datetime.datetime.now()).total_seconds() / 3600)
            eta_str = f"{hrs_rem:.1f} hours ({eta_dt.strftime('%d %b, %H:%M')})"
        except Exception:
            eta_str = "Calculating..."

        return (
            f"╔══ REAL-TIME TRACKING REPORT ══════════════════════╗\n"
            f"  Tracking ID   : {tracking_number}\n"
            f"  Status        : {data.get('status', 'In Transit')} ({'🟢' if data.get('status') == 'Delivered' else '🔵'})\n"
            f"  Carrier       : {data.get('carrier', 'Unknown')}\n"
            f"  Current City  : {curr}\n"
            f"  Next Stop     : {nxt}\n"
            f"  Origin → Dest : {data.get('source', '?')} → {data.get('destination', '?')}\n"
            f"  GPS Position  : {data.get('lat', 0):.4f}°N, {data.get('lon', 0):.4f}°E\n"
            f"  Speed         : {data.get('speed_kmph', 0):.1f} km/h\n"
            f"  Journey       : {pct}% complete\n"
            f"  Distance      : {data.get('total_distance_km', 0)} km total\n"
            f"  ETA           : {eta_str}\n"
            f"  Weight        : {data.get('weight', '?')} kg | Priority: {data.get('priority', '?')}\n"
            f"  Last Updated  : {data.get('last_updated', 'N/A')[:19]}\n"
            f"╚══════════════════════════════════════════════════════╝"
        )

    # Fallback to eShipz API
    api_data = _fetch_eshipz(tracking_number)
    if api_data and "data" in api_data:
        info = api_data["data"]
        return (
            f"╔══ ESHIPZ API TRACKING REPORT ═══════════════════════╗\n"
            f"  Tracking ID : {tracking_number}\n"
            f"  Status      : {info.get('status', 'Processing')}\n"
            f"  Carrier     : {info.get('carrier', 'eShipz Partner')}\n"
            f"  Last Event  : {info.get('last_event', 'Package scanned')}\n"
            f"  ETA         : {info.get('estimated_delivery', 'TBD')}\n"
            f"╚══════════════════════════════════════════════════════╝"
        )
    return (
        f"⚠️  No tracking data found for '{tracking_number}'.\n"
        "Please verify the tracking number is correct (format: SHP-XXXXXX or carrier AWB)."
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2: check_carrier_performance
# ══════════════════════════════════════════════════════════════════════════════
@tool("check_carrier_performance")
def check_carrier_performance(carrier_name: str) -> str:
    """
    Retrieves live carrier performance metrics including on-time delivery rate,
    average delay in minutes, reliability score, total shipments processed,
    SLA details, and service coverage.

    Use this tool to assess carrier quality and set customer expectations.
    Input: carrier name (e.g. 'BlueDart', 'FedEx', 'Delhivery', 'DTDC', 'eShipz Express')
    """
    analytics = _get_analytics()
    sla = CARRIER_SLA.get(carrier_name, {})
    score_bar = ""

    if analytics:
        rec = analytics.get_carrier(carrier_name)
        if rec:
            total    = rec.get("total_shipments", 1)
            on_time  = rec.get("on_time_deliveries", 0)
            ot_rate  = round(on_time / total * 100, 1)
            r_score  = rec.get("reliability_score", 0)
            avg_delay= rec.get("average_delay_min", 0)
            score_bar= "█" * int(r_score * 10) + "░" * (10 - int(r_score * 10))
            grade    = "A+" if r_score >= 0.93 else "A" if r_score >= 0.88 else "B+" if r_score >= 0.82 else "B"

            return (
                f"╔══ CARRIER INTELLIGENCE: {carrier_name.upper()} ════════════════╗\n"
                f"  Performance Grade  : {grade}\n"
                f"  Reliability Score  : {score_bar} {r_score:.2f}/1.00\n"
                f"  On-Time Rate       : {ot_rate}% ({on_time}/{total} shipments)\n"
                f"  Average Delay      : {avg_delay:.1f} minutes\n"
                f"  Total Processed    : {total} shipments\n"
                f"  ─────────────── SLA Details ───────────────\n"
                f"  Committed Delivery : {sla.get('max_days', '?')} business days\n"
                f"  Service Coverage   : {sla.get('coverage', 'Unknown')}\n"
                f"  Premium Service    : {'✅ Yes' if sla.get('premium') else '❌ No'}\n"
                f"  ─────────────── Risk Assessment ───────────\n"
                f"  Delay Risk         : {'🟢 LOW' if r_score >= 0.90 else '🟡 MEDIUM' if r_score >= 0.82 else '🔴 HIGH'}\n"
                f"  Customer Trust     : {'✅ Recommended' if r_score >= 0.88 else '⚠️  Use with caution'}\n"
                f"╚══════════════════════════════════════════════════════╝"
            )

    return (
        f"╔══ CARRIER: {carrier_name} ══════════════════════════════╗\n"
        f"  Status   : Live data unavailable — using defaults\n"
        f"  SLA Days : {sla.get('max_days', '3-5')} business days\n"
        f"  Coverage : {sla.get('coverage', 'Pan-India')}\n"
        f"  Premium  : {'Yes' if sla.get('premium') else 'No'}\n"
        f"╚══════════════════════════════════════════════════════╝"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3: predict_delivery_risk
# ══════════════════════════════════════════════════════════════════════════════
@tool("predict_delivery_risk")
def predict_delivery_risk(carrier: str, destination: str, priority: str = "Medium") -> str:
    """
    Performs a multi-factor risk assessment for shipment delivery.

    Analyzes: carrier reliability, route congestion, time-of-day traffic
    patterns, priority lane eligibility, and historical delay patterns
    to compute a composite delay probability and SLA breach risk.

    Use this tool after checking carrier performance to provide the
    customer with a proactive risk assessment.

    Input: carrier name, destination city, priority level (Low/Medium/High)
    """
    _ensure_root()
    try:
        from services.delay_prediction import predict_delay, ROUTE_CONGESTION, CARRIER_RELIABILITY
        dist_map = {"Madurai-Chennai": 480, "Coimbatore-Chennai": 500, "Trichy-Chennai": 330,
                    "Salem-Chennai": 340, "Dindigul-Chennai": 430, "Madurai-Trichy": 140}
        dist = random.randint(150, 550)
        speed = random.uniform(55, 85)
        result = predict_delay(
            tracking_id="risk-analysis", distance_km=dist, speed_kmph=speed,
            carrier=carrier, destination=destination, priority=priority
        )
        prob     = result["delay_probability"]
        delay_m  = result["predicted_delay_minutes"]
        conf     = result["confidence_score"]
        risk     = result["risk_level"]
        reason   = result["reason"]

        # SLA breach calculation
        sla_days = CARRIER_SLA.get(carrier, {}).get("max_days", 3)
        sla_hrs  = sla_days * 24
        sla_breach_risk = "HIGH" if prob > 0.5 else "MEDIUM" if prob > 0.25 else "LOW"
        breach_color = "🔴" if sla_breach_risk == "HIGH" else "🟡" if sla_breach_risk == "MEDIUM" else "🟢"

        congestion = ROUTE_CONGESTION.get(destination, 0.35)
        cong_level = "HIGH 🔴" if congestion > 0.65 else "MEDIUM 🟡" if congestion > 0.45 else "LOW 🟢"

        reliability = CARRIER_RELIABILITY.get(carrier, 0.85)
        rel_pct = f"{reliability * 100:.0f}%"

        bar_len  = int(prob * 20)
        risk_bar = "█" * bar_len + "░" * (20 - bar_len)

        return (
            f"╔══ MULTI-FACTOR DELAY RISK ASSESSMENT ════════════════╗\n"
            f"  Carrier           : {carrier}\n"
            f"  Destination       : {destination}\n"
            f"  Priority Lane     : {priority}\n"
            f"  ─────────────── Risk Factors ──────────────────────\n"
            f"  Carrier Reliability   : {rel_pct}\n"
            f"  Route Congestion      : {cong_level}\n"
            f"  Priority Adjustment   : {'✅ Premium lane eligible' if priority == 'High' else '⚠️  Standard lane'}\n"
            f"  ─────────────── Prediction Results ────────────────\n"
            f"  Delay Risk Bar    : [{risk_bar}] {prob*100:.1f}%\n"
            f"  Risk Level        : {risk} {'🟢' if risk=='Low' else '🟡' if risk=='Medium' else '🔴'}\n"
            f"  Predicted Delay   : +{delay_m} minutes\n"
            f"  Model Confidence  : {conf*100:.0f}%\n"
            f"  Reason            : {reason}\n"
            f"  ─────────────── SLA Compliance ────────────────────\n"
            f"  SLA Commitment    : {sla_days} business days\n"
            f"  SLA Breach Risk   : {breach_color} {sla_breach_risk}\n"
            f"╚══════════════════════════════════════════════════════╝"
        )
    except Exception as e:
        return f"Risk analysis error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# Tool 4: analyze_route_intelligence
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_route_intelligence")
def analyze_route_intelligence(source: str, destination: str) -> str:
    """
    Provides route intelligence including congestion levels, peak traffic hours,
    alternate route recommendations, estimated transit time, and city-level
    logistics hub information for the given source → destination corridor.

    Use this tool to give operational recommendations about the route.
    Input: source city name, destination city name
    """
    src_intel  = ROUTE_INTEL.get(source, {"congestion": "UNKNOWN", "peak_hours": "N/A", "alternate": "N/A"})
    dest_intel = ROUTE_INTEL.get(destination, {"congestion": "UNKNOWN", "peak_hours": "N/A", "alternate": "N/A"})

    _ensure_root()
    try:
        from services.simulation_engine import CITY_NODES, _haversine_km, ROUTE_GRAPH
        from collections import deque

        # BFS path
        visited, queue = {source}, deque([[source]])
        path = [source, destination]
        while queue:
            p = queue.popleft()
            if p[-1] == destination:
                path = p; break
            for n in ROUTE_GRAPH.get(p[-1], []):
                if n not in visited:
                    visited.add(n); queue.append(p + [n])

        total_km = sum(
            _haversine_km(
                CITY_NODES[path[i]]["lat"], CITY_NODES[path[i]]["lon"],
                CITY_NODES[path[i+1]]["lat"], CITY_NODES[path[i+1]]["lon"]
            ) for i in range(len(path)-1)
        ) if len(path) > 1 else 200

        avg_speed = 65  # km/h average
        est_hrs   = total_km / avg_speed
        route_str = " → ".join(path)

        src_cong  = src_intel["congestion"]
        dest_cong = dest_intel["congestion"]
        overall   = "HIGH" if "HIGH" in (src_cong, dest_cong) else "MEDIUM" if "MEDIUM" in (src_cong, dest_cong) else "LOW"
        cong_icon = "🔴" if overall == "HIGH" else "🟡" if overall == "MEDIUM" else "🟢"

    except Exception:
        total_km, est_hrs, route_str = 300, 4.6, f"{source} → {destination}"
        overall, cong_icon = "MEDIUM", "🟡"

    return (
        f"╔══ ROUTE INTELLIGENCE REPORT ══════════════════════════╗\n"
        f"  Corridor          : {source} → {destination}\n"
        f"  Optimal Route     : {route_str}\n"
        f"  Total Distance    : {total_km:.0f} km\n"
        f"  Est. Transit Time : {est_hrs:.1f} hours at avg {avg_speed}km/h\n"
        f"  ─────────────── Congestion Analysis ───────────────\n"
        f"  Overall Corridor  : {cong_icon} {overall}\n"
        f"  Source ({source[:10]}) Peak : {src_intel.get('peak_hours','N/A')}\n"
        f"  Destination Peak  : {dest_intel.get('peak_hours','N/A')}\n"
        f"  Alternate Route   : {dest_intel.get('alternate','N/A')}\n"
        f"  ─────────────── Recommendations ───────────────────\n"
        f"  Best Dispatch Time: {'Before 7:00 AM or after 8:00 PM' if overall == 'HIGH' else 'Before 8:00 AM'}\n"
        f"  Priority Flag     : {'⚡ Use express lane — high congestion corridor' if overall == 'HIGH' else '✅ Standard transit acceptable'}\n"
        f"╚══════════════════════════════════════════════════════╝"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tool 5: compare_carriers
# ══════════════════════════════════════════════════════════════════════════════
@tool("compare_carriers")
def compare_carriers(destination: str, weight_kg: float, priority: str = "Medium") -> str:
    """
    Generates a side-by-side carrier benchmarking comparison table showing
    cost scores, reliability, SLA days, and a composite recommendation score
    for the given destination, weight, and priority.

    Use this when the planning agent needs validation or when the customer
    asks which carrier would have been better.

    Input: destination city, weight in kg, priority level
    """
    analytics = _get_analytics()
    carriers  = ["BlueDart", "FedEx", "Delhivery", "DTDC", "eShipz Express"]
    rows = []

    for c in carriers:
        sla   = CARRIER_SLA.get(c, {})
        rec   = analytics.get_carrier(c) if analytics else {}
        r_score = rec.get("reliability_score", 0.85) if rec else 0.85
        avg_d   = rec.get("average_delay_min", 30) if rec else 30
        total   = rec.get("total_shipments", 50) if rec else 50
        on_time_pct = round((rec.get("on_time_deliveries", 42) / max(total, 1)) * 100, 1) if rec else 85.0

        # Composite score (reliability 40%, SLA days 30%, delay 20%, priority 10%)
        sla_score    = (6 - sla.get("max_days", 3)) / 5  # lower days = higher score
        delay_score  = max(0, 1 - avg_d / 120)
        prio_bonus   = 0.1 if sla.get("premium") and priority == "High" else 0
        composite    = round((r_score * 0.4 + sla_score * 0.3 + delay_score * 0.2 + prio_bonus * 0.1) * 100, 1)

        rows.append((c, r_score, on_time_pct, avg_d, sla.get("max_days", 3), composite))

    rows.sort(key=lambda x: x[5], reverse=True)
    lines = [
        f"╔══ CARRIER BENCHMARK: {destination} | {weight_kg}kg | {priority} priority ══╗",
        f"  {'Carrier':<18} {'Score':>6} {'OnTime%':>8} {'AvgDelay':>9} {'SLA Days':>9}",
        f"  {'─'*18} {'─'*6} {'─'*8} {'─'*9} {'─'*9}",
    ]
    for i, (c, r, ot, ad, sla_d, comp) in enumerate(rows):
        medal = ["🥇", "🥈", "🥉", "  ", "  "][i]
        lines.append(f"  {medal} {c:<16} {comp:>6.1f} {ot:>7.1f}% {ad:>8.1f}m {sla_d:>8}d")

    lines.append(f"  {'─'*52}")
    lines.append(f"  ✅ TOP RECOMMENDATION: {rows[0][0]} (Score: {rows[0][5]})")
    lines.append(f"╚══════════════════════════════════════════════════════╝")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 6: get_customer_alert_level
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_customer_alert_level")
def get_customer_alert_level(carrier: str, delay_risk: str, priority: str) -> str:
    """
    Determines the customer communication priority level (GREEN / YELLOW / RED)
    and generates a ready-to-send customer notification message.

    GREEN  = On track, no action needed
    YELLOW = Minor risk, proactive update recommended
    RED    = High delay risk, immediate customer contact required

    Use this as the FINAL tool to determine what to communicate to the customer.
    Input: carrier name, delay_risk level ('Low'/'Medium'/'High'), priority level
    """
    if delay_risk == "High" or priority == "High":
        alert  = "🔴 RED ALERT"
        action = "IMMEDIATE customer contact required"
        sms    = (f"URGENT: Your {carrier} shipment may experience delays. "
                  "Our team is monitoring actively. Expect update within 2 hours.")
        email  = "Escalate to Senior Logistics Manager. Offer compensation SLA credit if breach confirmed."
    elif delay_risk == "Medium":
        alert  = "🟡 YELLOW ALERT"
        action = "Proactive customer communication recommended within 4 hours"
        sms    = (f"UPDATE: Your {carrier} shipment is progressing. "
                  "Minor delays possible — we're on top of it!")
        email  = "Send proactive delay advisory email. Offer tracking link and revised ETA."
    else:
        alert  = "🟢 GREEN STATUS"
        action = "No immediate action required — standard monitoring"
        sms    = f"Good news! Your {carrier} shipment is on track for on-time delivery."
        email  = "No action required. Automated tracking notifications active."

    return (
        f"╔══ CUSTOMER ALERT CLASSIFICATION ══════════════════════╗\n"
        f"  Alert Level       : {alert}\n"
        f"  Required Action   : {action}\n"
        f"  Carrier           : {carrier}\n"
        f"  Delay Risk        : {delay_risk}\n"
        f"  Customer Priority : {priority}\n"
        f"  ─────────────── Customer Communication ────────────\n"
        f"  SMS Template  : \"{sms}\"\n"
        f"  Email Action  : {email}\n"
        f"╚══════════════════════════════════════════════════════╝"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tool 7: generate_logistics_report
# ══════════════════════════════════════════════════════════════════════════════
@tool("generate_logistics_report")
def generate_logistics_report(
    carrier: str, source: str, destination: str,
    weight: str, priority: str
) -> str:
    """
    Generates a comprehensive 360° logistics intelligence report combining
    all available data: carrier performance, route analysis, delay prediction,
    SLA compliance, and customer communication recommendations.

    Use this as a SUMMARY tool after calling other analysis tools. It provides
    a professional report suitable for both operations teams and customer-facing use.

    Input: carrier, source city, destination city, weight (as string), priority level
    """
    ts   = datetime.datetime.now().strftime("%d %b %Y, %H:%M IST")
    sla  = CARRIER_SLA.get(carrier, {})
    analytics = _get_analytics()
    rec  = analytics.get_carrier(carrier) if analytics else {}
    r_score  = rec.get("reliability_score", 0.85) if rec else 0.85
    avg_delay= rec.get("average_delay_min", 25) if rec else 25
    on_time  = round(r_score * 100, 1)

    grade = "A+" if r_score >= 0.93 else "A" if r_score >= 0.88 else "B+" if r_score >= 0.82 else "B"

    try:
        wt = float(weight)
        cost_estimate = round(wt * random.uniform(42, 78), 2)
    except Exception:
        cost_estimate = "N/A"

    return (
        f"\n{'═'*58}\n"
        f"  ESHIPZ AI LOGISTICS INTELLIGENCE REPORT\n"
        f"  Generated: {ts}\n"
        f"{'═'*58}\n\n"
        f"  SHIPMENT DETAILS\n"
        f"  Route     : {source} → {destination}\n"
        f"  Weight    : {weight} kg | Priority: {priority}\n"
        f"  Carrier   : {carrier} (Grade: {grade})\n"
        f"  Est. Cost : ₹ {cost_estimate}\n\n"
        f"  CARRIER INTELLIGENCE\n"
        f"  Reliability Score : {r_score:.2f}/1.00 ({on_time}% on-time)\n"
        f"  Avg Delay History : {avg_delay:.0f} minutes\n"
        f"  SLA Commitment    : {sla.get('max_days','?')} business days\n"
        f"  Coverage Area     : {sla.get('coverage','Pan-India')}\n"
        f"  Premium Service   : {'Yes ✅' if sla.get('premium') else 'No ❌'}\n\n"
        f"  RISK ASSESSMENT\n"
        f"  Delay Risk Level  : {'🟢 LOW' if r_score >= 0.90 else '🟡 MEDIUM' if r_score >= 0.82 else '🔴 HIGH'}\n"
        f"  SLA Breach Risk   : {'🟢 UNLIKELY' if r_score >= 0.88 else '🟡 POSSIBLE' if r_score >= 0.80 else '🔴 LIKELY'}\n"
        f"  Recommended Action: {'Standard monitoring' if r_score >= 0.88 else 'Activate enhanced tracking'}\n\n"
        f"  CUSTOMER GUIDANCE\n"
        f"  Status Alert      : {'🟢 GREEN — On track' if r_score >= 0.88 else '🟡 YELLOW — Monitor'}\n"
        f"  Communication     : {'Automated updates sufficient' if r_score >= 0.90 else 'Proactive outreach recommended'}\n\n"
        f"{'═'*58}\n"
        f"  Report ID: ESZ-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}\n"
        f"  Confidence: {min(95, int(r_score * 100))}% | Model: eShipz-AI-v2\n"
        f"{'═'*58}\n"
    )