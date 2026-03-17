"""
Single-Shot Shipment Processor — 1 API call replaces 6.

Architecture:
  OLD: planning_agent (LLM) + booking_agent (LLM) + tracking_agent (LLM × 4)
       = ~6 API calls

  NEW: AWB generation (pure Python, 0 API calls)
       + Barcode generation (pure Python, 0 API calls)
       + ONE comprehensive Gemini API call that does:
           • carrier selection with justification
           • route analysis
           • delay risk assessment
           • carrier performance benchmarking
           • customer alert classification
           • logistics intelligence report
       = 1 API call total
"""

import os
import re
import random
import string
import datetime
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.india_network import INDIA_CITIES, bfs_route, route_distance_km
from services.carrier_analytics import get_analytics
from services.simulation_engine import get_simulator

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL     = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key={key}"
)

# ── Carrier SLA data (available without any API call) ─────────────────────────
CARRIER_SLA = {
    "BlueDart":       {"max_days": 2, "premium": True,  "coverage": "Pan-India"},
    "FedEx":          {"max_days": 3, "premium": True,  "coverage": "International"},
    "Delhivery":      {"max_days": 4, "premium": False, "coverage": "Pan-India"},
    "DTDC":           {"max_days": 5, "premium": False, "coverage": "Regional"},
    "Eshipz Express": {"max_days": 3, "premium": True,  "coverage": "South India"},
}

CARRIERS = list(CARRIER_SLA.keys())


# ── Step 1: Pure-Python AWB generator (0 API calls) ───────────────────────────
def generate_awb(carrier: str) -> str:
    prefix = carrier[:3].upper().replace(" ", "")
    digits = "".join(random.choices(string.digits, k=10))
    return f"{prefix}-{digits}"


# ── Step 2: Pure-Python barcode generator (0 API calls) ───────────────────────
def generate_barcode_label(awb: str) -> str:
    try:
        import barcode
        from barcode.writer import ImageWriter
        code = barcode.get("code128", awb, writer=ImageWriter())
        filename = f"shipping_label_{awb}"
        code.save(filename)
        
        # Upload to AWS S3
        import boto3
        import os
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'ap-south-1')
        )
        bucket_name = os.getenv('AWS_S3_BUCKET', 'eshipz-barcodes')
        file_path = f"{filename}.png"
        s3.upload_file(file_path, bucket_name, file_path)
        url = f"https://{bucket_name}.s3.{os.getenv('AWS_REGION', 'ap-south-1')}.amazonaws.com/{file_path}"
        
        return f"✅ Barcode saved and uploaded to S3: {url}"
    except Exception as e:
        return f"Barcode generation/upload skipped: {e}"


def _get_closest_city(city_name: str) -> str:
    if city_name in INDIA_CITIES: return city_name
    from geopy.geocoders import Nominatim
    from services.india_network import haversine_km
    try:
        geolocator = Nominatim(user_agent="eshipz_logistics_app")
        location = geolocator.geocode(f"{city_name}, India")
        if not location: return "Delhi"

        lat, lon = location.latitude, location.longitude
        closest_city = "Delhi"
        min_dist = float('inf')

        for name, coords in INDIA_CITIES.items():
            dist = haversine_km(lat, lon, coords["lat"], coords["lon"])
            if dist < min_dist:
                min_dist = dist
                closest_city = name
                
        return closest_city
    except Exception:
        return "Delhi"

# ── Step 3: Build data context (0 API calls) ───────────────────────────────────
def _build_context(source: str, dest: str, weight: float, priority: str) -> dict:
    true_source = source
    true_dest = dest
    
    source = _get_closest_city(source)
    dest = _get_closest_city(dest)
    
    analytics     = get_analytics()
    perf_rows     = analytics.summary_table()
    route         = bfs_route(source, dest)
    total_dist_km = route_distance_km(route)

    carrier_data = []
    for c in CARRIERS:
        sla = CARRIER_SLA[c]
        r   = next((x for x in perf_rows if x.get("Carrier") == c), {})
        carrier_data.append({
            "name":        c,
            "sla_days":    sla["max_days"],
            "premium":     sla["premium"],
            "reliability": r.get("Reliability Score", 0.85),
            "on_time_pct": r.get("On-Time Rate (%)", 85.0),
            "avg_delay":   r.get("Avg Delay (min)", 30),
        })

    # Sort by composite score for context
    for c in carrier_data:
        c["score"] = round(
            c["reliability"] * 0.4 +
            ((6 - c["sla_days"]) / 5) * 0.3 +
            max(0, 1 - c["avg_delay"] / 120) * 0.2 +
            (0.1 if c["premium"] and priority == "High" else 0) * 0.1,
            3
        )
    carrier_data.sort(key=lambda x: x["score"], reverse=True)

    src_city = INDIA_CITIES.get(source, {})
    dst_city = INDIA_CITIES.get(dest, {})

    return {
        "source":       true_source,
        "dest":         true_dest,
        "mapped_src":   source,
        "mapped_dst":   dest,
        "weight":       weight,
        "priority":     priority,
        "route":        " → ".join(route),
        "dist_km":      total_dist_km,
        "src_zone":     src_city.get("zone", "Unknown"),
        "dst_zone":     dst_city.get("zone", "Unknown"),
        "src_cong":     src_city.get("congestion", 0.5),
        "dst_cong":     dst_city.get("congestion", 0.5),
        "carriers":     carrier_data,
        "timestamp":    datetime.datetime.now().strftime("%d %b %Y, %H:%M IST"),
    }


# ── Step 4: ONE Gemini API call ────────────────────────────────────────────────
def _call_gemini_once(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return None  # Fall back to rule-based output

    url = GEMINI_URL.format(key=GEMINI_API_KEY)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":    0.4,
            "maxOutputTokens": 1200,
            "topK": 20,
            "topP": 0.85,
        }
    }
    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return None   # Caller will use rule-based fallback


def _build_prompt(ctx: dict, awb: str) -> str:
    carriers_txt = "\n".join(
        f"  {i+1}. {c['name']}: reliability={c['reliability']:.2f}, "
        f"on_time={c['on_time_pct']:.1f}%, avg_delay={c['avg_delay']}min, "
        f"sla={c['sla_days']}d, score={c['score']:.3f}"
        for i, c in enumerate(ctx["carriers"])
    )
    return f"""You are the Eshipz AI Logistics Intelligence System. Generate a comprehensive shipment report.

SHIPMENT DETAILS:
- Route: {ctx['source']} (Mapped to {ctx['mapped_src']} Hub, {ctx['src_zone']} Zone) → {ctx['dest']} (Mapped to {ctx['mapped_dst']} Hub, {ctx['dst_zone']} Zone)
- Distance: {ctx['dist_km']:.0f} km via {ctx['route']}
- Weight: {ctx['weight']} kg | Priority: {ctx['priority']}
- AWB Generated: {awb}
- Timestamp: {ctx['timestamp']}

LIVE CARRIER PERFORMANCE DATA:
{carriers_txt}

ROUTE CONGESTION:
- Source ({ctx['source']}): {ctx['src_cong']*100:.0f}% congestion index
- Destination ({ctx['dest']}): {ctx['dst_cong']*100:.0f}% congestion index

Generate a structured logistics intelligence report with these EXACTLY labeled sections:

## 🎯 CARRIER SELECTION
State the chosen carrier and runner-up. Give 3 specific data-driven reasons.

## 📦 BOOKING CONFIRMATION
Confirm AWB: {awb}. State estimated cost in ₹ (weight × rate per kg). Confirm barcode generated.

## 🗺️ ROUTE INTELLIGENCE
Analyze the {ctx['route']} corridor. Mention congestion, best dispatch time, estimated transit hours.

## ⚠️ DELAY RISK ASSESSMENT
Give a delay probability (%) and risk level (Low/Medium/High) based on carrier reliability and route congestion. Give specific reason.

## 📊 CARRIER BENCHMARKS
Rank all 5 carriers for this shipment. One line each.

## 🔔 CUSTOMER ALERT
Classify as GREEN/YELLOW/RED. Give a ready-to-send SMS notification message.

## 📋 EXECUTIVE SUMMARY
Two-sentence overall assessment. End with: Report ID: ESZ-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}

Be specific, data-driven, and concise. Total response: 400-600 words max."""


# ── Step 5: Rule-based fallback (0 API calls — never fails) ───────────────────
def _rule_based_report(ctx: dict, awb: str) -> str:
    best    = ctx["carriers"][0]
    second  = ctx["carriers"][1]
    carrier = best["name"]
    sla     = CARRIER_SLA[carrier]
    dist    = ctx["dist_km"]
    speed   = {"High": 85, "Medium": 65, "Low": 50}.get(ctx["priority"], 65)
    est_h   = round(dist / speed, 1)
    cost    = round(ctx["weight"] * random.uniform(45, 75), 2)
    delay_p = round((1 - best["reliability"]) * 100, 1)
    risk    = "Low" if delay_p < 15 else "Medium" if delay_p < 30 else "High"
    alert   = "🟢 GREEN" if risk == "Low" else "🟡 YELLOW" if risk == "Medium" else "🔴 RED"
    sms_msg = (f"Your {carrier} shipment ({awb}) from {ctx['source']} to {ctx['dest']} "
               f"is confirmed. ETA: {sla['max_days']} business days.")

    carrier_ranks = "\n".join(
        f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '  '} "
        f"{c['name']}: Score {c['score']:.3f} | {c['on_time_pct']:.1f}% on-time | {c['sla_days']}d SLA"
        for i, c in enumerate(ctx["carriers"])
    )

    return f"""
## 🎯 CARRIER SELECTION
**Selected: {carrier}** (Runner-up: {second['name']})
1. Highest composite score: {best['score']:.3f} vs {second['score']:.3f}
2. {best['on_time_pct']:.1f}% on-time delivery rate — best in class for {ctx['priority']} priority
3. {sla['max_days']}-day SLA commitment{'  + Premium service lane eligible' if sla['premium'] and ctx['priority'] == 'High' else ''}

## 📦 BOOKING CONFIRMATION
- **AWB:** `{awb}`
- **Estimated Cost:** ₹ {cost} ({ctx['weight']} kg × ₹{round(cost/ctx['weight'],2)}/kg)
- **Barcode:** shipping_label.png ✅
- **Departure:** {datetime.datetime.now().strftime('%d %b %Y, %H:%M IST')}

## 🗺️ ROUTE INTELLIGENCE
**Corridor:** {ctx['route']}
- True Origin: {ctx['source']} | True Destination: {ctx['dest']}
- Distance: **{dist:.0f} km** | Est. transit: **{est_h} hours** at {speed} km/h
- Source congestion: **{ctx['src_cong']*100:.0f}%** | Destination: **{ctx['dst_cong']*100:.0f}%**
- Best dispatch time: {'Before 7:00 AM (high congestion)' if ctx['src_cong'] > 0.7 else 'Before 8:00 AM (standard)'}

## ⚠️ DELAY RISK ASSESSMENT
- **Risk Level:** {risk} {'🟢' if risk=='Low' else '🟡' if risk=='Medium' else '🔴'}
- **Delay Probability:** {delay_p:.1f}%
- **Predicted Extra Time:** {round(delay_p * 0.8)} minutes
- **Reason:** {carrier} has {best['avg_delay']}min avg delay on {ctx['src_zone']}→{ctx['dst_zone']} corridors.

## 📊 CARRIER BENCHMARKS
{carrier_ranks}

## 🔔 CUSTOMER ALERT
**Status: {alert}**
SMS: "{sms_msg}"

## 📋 EXECUTIVE SUMMARY
{carrier} is the optimal carrier for this {ctx['weight']}kg {ctx['priority']}-priority shipment from {ctx['source']} to {ctx['dest']}, delivering a {sla['max_days']}-day SLA with {best['on_time_pct']:.1f}% on-time performance. Delay risk is **{risk}** — {'no action required.' if risk == 'Low' else 'monitor proactively.'}

Report ID: ESZ-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')} | Confidence: {min(98, int(best['reliability']*100))}%
"""


# ── Public entry point ─────────────────────────────────────────────────────────
def process_shipment_single_shot(
    source: str, destination: str, weight: float, priority: str,
    user_id: int = 0, db=None
) -> dict:
    """
    Process a shipment in a SINGLE API call (or zero if API unavailable).

    Returns:
        {
            "awb":          str,
            "carrier":      str,
            "tracking_id":  str,
            "report":       str (markdown),
            "barcode_msg":  str,
            "used_api":     bool,
        }
    """
    # ── 0 API calls: build context from live data ─────────────────────────────
    ctx     = _build_context(source, destination, weight, priority)
    
    # ── Apply business logic to select best carrier based on weight/priority ──
    # Default is the highest scored carrier (idx 0)
    best_carrier_idx = 0
    
    if priority in ["High", "Urgent"]:
        # Find highest score among express carriers
        for i, c in enumerate(ctx["carriers"]):
            if c["name"] == "Delhivery" or c["premium"]:
                best_carrier_idx = i
                break
    elif weight <= 2.0:
        for i, c in enumerate(ctx["carriers"]):
            if c["name"] == "BlueDart":
                best_carrier_idx = i
                break
    elif 2.0 < weight <= 5.0:
        for i, c in enumerate(ctx["carriers"]):
            if c["name"] == "DTDC":
                best_carrier_idx = i
                break
    elif weight > 5.0:
        for i, c in enumerate(ctx["carriers"]):
            if c["name"] == "FedEx":
                best_carrier_idx = i
                break
                
    carrier = ctx["carriers"][best_carrier_idx]["name"]

    # ── 0 API calls: generate AWB + barcode ───────────────────────────────────
    awb         = generate_awb(carrier)
    barcode_msg = generate_barcode_label(awb)

    # ── 1 API call (or 0 if key missing/quota hit) ────────────────────────────
    prompt    = _build_prompt(ctx, awb)
    llm_text  = _call_gemini_once(prompt)
    used_api  = llm_text is not None

    if llm_text:
        report = llm_text
        # Try to extract carrier from LLM response
        m = re.search(r"Selected:\s*\*?\*?([A-Za-z ]+?)\*?\*?[\s\n\(]", llm_text)
        if m:
            found = m.group(1).strip()
            if found in CARRIER_SLA:
                carrier = found
    else:
        # Fully rule-based — no API call at all
        report = _rule_based_report(ctx, awb)

    # ── 0 API calls: start simulation ─────────────────────────────────────────
    tracking_id = ""
    try:
        sim = get_simulator(db=db)
        tracking_id = sim.create_shipment(
            source=source, destination=destination,
            carrier=carrier, weight=weight,
            priority=priority, user_id=user_id
        )
    except Exception:
        pass

    return {
        "awb":         awb,
        "carrier":     "Pending",   # Admin must assign the actual carrier
        "ai_carrier":  carrier,     # AI recommendation (shown in report only)
        "tracking_id": tracking_id,
        "report":      report,
        "barcode_msg": barcode_msg,
        "used_api":    used_api,
        "route":       ctx["route"],
        "dist_km":     ctx["dist_km"],
    }
