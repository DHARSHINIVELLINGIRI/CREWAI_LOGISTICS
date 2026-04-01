import requests
import json
import datetime
import barcode
from barcode.writer import ImageWriter
import random
import string
import os
from pathlib import Path
from crewai.tools import tool
from dotenv import load_dotenv

# ── ABSOLUTE PATH .env loader ─────────────────────────────────────────────────
# Plain load_dotenv() breaks when CrewAI/Streamlit changes the working directory.
# We walk up from this file's location until we find the .env that contains the token.
_THIS_FILE = Path(__file__).resolve()
_token_loaded = False

for _candidate in [
    _THIS_FILE.parent / ".env",                      # src/shipment/tools/.env
    _THIS_FILE.parent.parent / ".env",               # src/shipment/.env
    _THIS_FILE.parent.parent.parent / ".env",        # src/.env
    _THIS_FILE.parent.parent.parent.parent / ".env", # project root  ← most likely
]:
    if _candidate.exists():
        load_dotenv(dotenv_path=_candidate, override=True)
        if os.getenv("ESHIPZ_API_KEY", "").strip():
            _token_loaded = True
            break   # stop at the first .env that actually contains the token


@tool("track_shipment_eshipz")
def track_shipment_eshipz(track_id: str):
    """
    Fetches real-time tracking data from the eShipz V2 API.
    Payload: {"track_id": "<id>"}  — no include_split (confirmed via Postman).
    Returns a JSON string (list of shipment dicts with checkpoints) or an error string.
    """
    # Accept either env var name (ESHIPZ_API_KEY in .env, ESHIPZ_API_TOKEN in some configs)
    api_token = (os.getenv("ESHIPZ_API_TOKEN") or os.getenv("ESHIPZ_API_KEY") or "").strip()

    if not api_token:
        tried_paths = " | ".join([
            str(_THIS_FILE.parent / ".env"),
            str(_THIS_FILE.parent.parent / ".env"),
            str(_THIS_FILE.parent.parent.parent / ".env"),
            str(_THIS_FILE.parent.parent.parent.parent / ".env"),
        ])
        return (
            f"Configuration Error: Neither ESHIPZ_API_TOKEN nor ESHIPZ_API_KEY found in environment. "
            f"Searched .env files: {tried_paths}"
        )
    print(f"[tool_serve] eShipz token loaded OK ({api_token[:6]}...)")

    url = "https://app.eshipz.com/api/v2/trackings"
    headers = {
        "Content-Type": "application/json",
        "X-API-TOKEN": api_token,
    }
    payload = {"track_id": str(track_id)}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)

        if response.status_code == 200:
            data = response.json()

            # Empty list [] or {"Count": 0} → no record for this ID
            if not data or (isinstance(data, dict) and data.get("Count") == 0):
                return (
                    f"System Check: API connected successfully. "
                    f"No records found for ID {track_id}."
                )

            return json.dumps(data)

        else:
            return (
                f"Server Alert: HTTP {response.status_code}. "
                f"Body: {response.text[:300]}"
            )

    except requests.exceptions.Timeout:
        return "Network Error: Request timed out after 20 seconds."
    except Exception as e:
        return f"Network Error: {str(e)}"


@tool("generate_barcode")
def generate_barcode(awb_number: str):
    """Generates a physical barcode image (PNG) for the given AWB number."""
    try:
        code128 = barcode.get('code128', str(awb_number), writer=ImageWriter())
        os.makedirs('labels', exist_ok=True)
        filename = f"labels/label_{awb_number}"
        full_path = code128.save(filename)
        return f"SUCCESS: Physical barcode generated at: {full_path}"
    except Exception as e:
        return f"Barcode Error: {str(e)}"


@tool("awb_generator")
def awb_generator(carrier: str):
    """Generates a unique AWB number dynamically based on carrier name."""
    prefix = str(carrier)[:3].upper()
    digits = ''.join(random.choices(string.digits, k=10))
    return f"{prefix}-{digits}"


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4 TOOL: Bulk Shipment Fetcher (Logistics Supervisor)
# ══════════════════════════════════════════════════════════════════════════════

@tool("fetch_shipments_by_date")
def fetch_shipments_by_date(min_date: str, max_date: str, page: str = "1", limit: str = "50"):
    """
    Fetches shipments from the eShipz API for a given date range.
    Use this to retrieve bulk shipment data for monitoring and filtering.

    Parameters:
        min_date: Start date in YYYY-MM-DD format (e.g. '2026-03-01')
        max_date: End date in YYYY-MM-DD format (e.g. '2026-03-31')
        page: Page number for pagination (default: '1')
        limit: Number of results per page (default: '50')

    Returns a JSON string with shipment data or an error message.
    """
    api_token = (os.getenv("ESHIPZ_API_TOKEN") or os.getenv("ESHIPZ_API_KEY") or "").strip()

    if not api_token:
        return "Configuration Error: No eShipz API token found in environment."

    url = "https://app.eshipz.com/api/v2/get-shipments"
    headers = {
        "Content-Type": "application/json",
        "X-API-TOKEN": api_token,
    }
    params = {
        "min_date": str(min_date),
        "max_date": str(max_date),
        "page": int(page),
        "limit": int(limit),
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if not data:
                return json.dumps({
                    "message": f"No shipments found between {min_date} and {max_date}.",
                    "shipments": []
                })
            return json.dumps(data)
        else:
            return (
                f"Server Alert: HTTP {response.status_code}. "
                f"Body: {response.text[:300]}"
            )
    except requests.exceptions.Timeout:
        return "Network Error: Request timed out after 30 seconds."
    except Exception as e:
        return f"Network Error: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5 TOOL: Shipment Intelligence Analyzer
# ══════════════════════════════════════════════════════════════════════════════

EXCEPTION_STATUSES = {
    "exception", "undelivered", "failed", "failed delivery",
    "delivery failed", "undeliverable",
}
RETURN_STATUSES = {
    "rto", "rto initiated", "return", "return in transit",
    "returned", "return to origin",
}


@tool("analyze_shipment_intelligence")
def analyze_shipment_intelligence(shipment_json: str):
    """
    Performs deep analysis on a single shipment to detect delays, stuck packages,
    high-risk situations, and movement discrepancies. Uses Python logic only.

    Input: A JSON string of a single shipment object with fields like
    tracking_number, tag/status, expected_delivery_date, checkpoints, etc.

    Returns a JSON string with analysis results: status, issues, prediction.
    The LLM agent should then generate a human-readable explanation.
    """
    try:
        shipment = json.loads(shipment_json) if isinstance(shipment_json, str) else shipment_json
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON input"})

    order_id = (
        shipment.get("order_id")
        or shipment.get("tracking_number")
        or shipment.get("awb")
        or "Unknown"
    )
    current_tag = (
        shipment.get("tag") or shipment.get("status")
        or shipment.get("current_status") or ""
    ).lower()
    checkpoints = (
        shipment.get("checkpoints")
        or shipment.get("tracking_events")
        or shipment.get("events")
        or shipment.get("scans")
        or []
    )

    issues = []
    status_label = "On-Time"
    prediction = "Will be delivered"
    now = datetime.datetime.now()

    # ── 1. Delay Detection ───────────────────────────────────────────────────
    exp_del_raw = shipment.get("expected_delivery_date") or shipment.get("expected_delivery") or ""
    delay_days = 0
    if exp_del_raw:
        try:
            from email.utils import parsedate_to_datetime
            exp_date = parsedate_to_datetime(str(exp_del_raw))
        except Exception:
            exp_date = None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    exp_date = datetime.datetime.strptime(str(exp_del_raw).strip(), fmt)
                    break
                except Exception:
                    pass

        if exp_date:
            delay_days = (now - exp_date).days
            if delay_days > 5:
                status_label = "Delayed"
                issues.append(f"Shipment is {delay_days} days past expected delivery date")

    # ── 2. Stuck Detection ───────────────────────────────────────────────────
    if checkpoints:
        # Check for same hub appearing 3+ times in the last 10 events
        recent = checkpoints[:10]
        hub_counts = {}
        for cp in recent:
            hub = (cp.get("city") or cp.get("location") or cp.get("place") or "").strip().lower()
            if hub:
                hub_counts[hub] = hub_counts.get(hub, 0) + 1

        repeated_hubs = [h for h, c in hub_counts.items() if c >= 3]
        if repeated_hubs:
            status_label = "Stuck"
            issues.append(f"Shipment stuck at same hub: {', '.join(repeated_hubs).title()} (appeared 3+ times)")

        # Check for no movement in 48+ hours
        try:
            latest_date_raw = (
                checkpoints[0].get("checkpoint_time")
                or checkpoints[0].get("date")
                or checkpoints[0].get("timestamp")
                or ""
            )
            if latest_date_raw:
                try:
                    from email.utils import parsedate_to_datetime
                    latest_dt = parsedate_to_datetime(str(latest_date_raw))
                except Exception:
                    latest_dt = None
                    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                                "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
                        try:
                            latest_dt = datetime.datetime.strptime(str(latest_date_raw).strip(), fmt)
                            break
                        except Exception:
                            pass

                if latest_dt:
                    # Make naive for comparison
                    if latest_dt.tzinfo is not None:
                        latest_dt = latest_dt.replace(tzinfo=None)
                    hours_since = (now - latest_dt).total_seconds() / 3600
                    if hours_since > 48:
                        if status_label != "Stuck":
                            status_label = "Stuck"
                        issues.append(f"No movement for {int(hours_since)} hours (>{48}h threshold)")
        except Exception:
            pass

    # ── 3. Risk Prediction ───────────────────────────────────────────────────
    # Count undelivered/failed delivery attempts
    failed_attempts = 0
    for cp in checkpoints:
        cp_tag = (cp.get("tag") or cp.get("status") or cp.get("activity") or "").lower()
        if any(kw in cp_tag for kw in ("failed", "undeliver", "delivery attempt", "not delivered")):
            failed_attempts += 1

    if failed_attempts >= 2:
        status_label = "High Risk"
        issues.append(f"Repeated delivery failures ({failed_attempts} failed attempts)")
        prediction = "Likely to be returned"

    # Check if return process initiated
    if any(kw in current_tag for kw in ("rto", "return")):
        status_label = "High Risk"
        issues.append("Return/RTO process has been initiated")
        prediction = "Likely to be returned"

    # ── 4. Movement Discrepancy Analysis ─────────────────────────────────────
    ofd_count = 0
    hub_sequence = []
    for cp in checkpoints:
        cp_tag = (cp.get("tag") or cp.get("status") or cp.get("activity") or "").lower()
        hub = (cp.get("city") or cp.get("location") or "").strip().lower()

        if "out for delivery" in cp_tag or "outfordelivery" in cp_tag:
            ofd_count += 1
        if hub:
            hub_sequence.append(hub)

    if ofd_count >= 3:
        issues.append(f"Repeated 'Out for Delivery' attempts ({ofd_count} times) — delivery address issue likely")

    # Detect hub looping (A → B → A pattern)
    if len(hub_sequence) >= 4:
        for i in range(len(hub_sequence) - 3):
            if (hub_sequence[i] == hub_sequence[i + 2] and
                    hub_sequence[i + 1] == hub_sequence[i + 3]):
                issues.append(f"Hub looping detected: {hub_sequence[i].title()} ↔ {hub_sequence[i+1].title()}")
                break

    # ── Build output ─────────────────────────────────────────────────────────
    if not issues:
        issues.append("No anomalies detected — shipment appears to be progressing normally")

    if status_label in ("Delayed", "Stuck", "High Risk") and prediction == "Will be delivered":
        prediction = "Delivery at risk — may require intervention"

    result = {
        "order_id": order_id,
        "status": status_label,
        "delay_days": delay_days if delay_days > 0 else 0,
        "failed_attempts": failed_attempts,
        "total_checkpoints": len(checkpoints),
        "issues": issues,
        "prediction": prediction,
        "explanation": "[LLM agent should provide human-readable reasoning based on the above data]",
    }

    return json.dumps(result, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT ENGINE — Bulk Shipment Intelligence Pipeline
# ══════════════════════════════════════════════════════════════════════════════
#
# 🚨 ARCHITECTURE RULE (NON-NEGOTIABLE):
#   Step 1: Fetch shipment list from SQLite ONLY (user_shipments table)
#   Step 2: For EACH AWB → call eShipz Tracking API (POST /trackings)
#   Step 3: Run Python-based intelligence analysis (delay/stuck/risk)
#   Step 4: Return results for Streamlit dashboard
#
# ❌ MongoDB is NEVER used in this pipeline.
# ❌ No stored/cached status data — only LIVE tracking API responses.
# ══════════════════════════════════════════════════════════════════════════════

def fetch_shipments_direct(min_date: str, max_date: str, limit: int = 50) -> list:
    """
    Fetches the shipment LIST from SQLite (user_shipments table) ONLY.
    Returns AWB / tracking IDs + metadata for the enrichment engine.

    ❌ Does NOT fetch shipment status — status comes from eShipz API later.
    ❌ Does NOT use MongoDB under any circumstance.
    """
    import sqlite3

    # Locate the SQLite database (data/eshipz_auth.db)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "eshipz_auth.db")
    db_path = os.path.normpath(db_path)

    # Fallback: try common locations relative to CWD
    if not os.path.exists(db_path):
        for candidate in [
            os.path.join(os.getcwd(), "data", "eshipz_auth.db"),
        ]:
            if os.path.exists(candidate):
                db_path = candidate
                break

    if not os.path.exists(db_path):
        print(f"[fetch_shipments_direct] ❌ SQLite DB not found at {db_path}")
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT tracking_id, awb, source, destination, weight, priority,
                      carrier, status, agent_output, created_at
               FROM user_shipments
               WHERE date(created_at) >= date(?) AND date(created_at) <= date(?)
               ORDER BY created_at DESC
               LIMIT ?""",
            (min_date, max_date, limit),
        ).fetchall()
        conn.close()

        shipments = []
        for r in rows:
            d = dict(r)
            # Normalize field names for the enrichment engine
            d["tracking_number"] = d.get("awb") or d.get("tracking_id") or ""
            d["order_id"] = d.get("tracking_id") or ""
            # Tag is set to a placeholder — REAL status comes from eShipz API in Step 2
            d["tag"] = "Pending Tracking"
            shipments.append(d)

        print(f"[fetch_shipments_direct] ✅ SQLite → {len(shipments)} shipment(s) in {min_date} → {max_date}")
        return shipments
    except Exception as e:
        print(f"[fetch_shipments_direct] ❌ SQLite error: {e}")
        return []

def _fetch_tracking_direct(track_id: str) -> dict | None:
    """Direct API call to eShipz tracking endpoint. Returns parsed JSON or None."""
    api_token = (os.getenv("ESHIPZ_API_TOKEN") or os.getenv("ESHIPZ_API_KEY") or "").strip()
    if not api_token:
        return None
    try:
        resp = requests.post(
            "https://app.eshipz.com/api/v2/trackings",
            json={"track_id": str(track_id)},
            headers={"Content-Type": "application/json", "X-API-TOKEN": api_token},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and not (isinstance(data, dict) and data.get("Count") == 0):
                return data
    except Exception:
        pass
    return None


def _run_analysis_pure(shipment: dict) -> dict:
    """
    Run delayed/stuck/risk analysis on a single shipment dict (must have checkpoints).
    Returns a dict with status, delay_days, stuck flag, issues, etc.
    Pure Python — no LLM calls.
    """
    now = datetime.datetime.now()

    # Prefer the most specific status field; fall back through alternatives
    current_tag = (
        shipment.get("tag") or shipment.get("status")
        or shipment.get("current_status") or shipment.get("tracking_status")
        or shipment.get("order_status") or ""
    ).lower()
    checkpoints_raw = (
        shipment.get("checkpoints")
        or shipment.get("tracking_events")
        or shipment.get("events")
        or shipment.get("scans")
    )
    if not checkpoints_raw and shipment.get("trackings") and isinstance(shipment["trackings"], list):
        checkpoints_raw = shipment["trackings"][0].get("checkpoints")
    checkpoints = checkpoints_raw or []
    order_id = (
        shipment.get("order_id")
        or shipment.get("tracking_number")
        or shipment.get("awb")
        or "Unknown"
    )
    awb = (
        shipment.get("tracking_number")
        or shipment.get("awb")
        or order_id
    )

    issues = []
    is_delayed = False
    is_stuck = False
    is_high_risk = False
    delay_days = 0
    last_movement_time = None
    repeated_hubs = []

    # ── Delay Detection ──────────────────────────────────────────────────────
    exp_del_raw = shipment.get("expected_delivery_date") or shipment.get("expected_delivery") or ""
    if exp_del_raw:
        exp_date = None
        try:
            from email.utils import parsedate_to_datetime
            exp_date = parsedate_to_datetime(str(exp_del_raw))
        except Exception:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    exp_date = datetime.datetime.strptime(str(exp_del_raw).strip(), fmt)
                    break
                except Exception:
                    pass
        if exp_date:
            if exp_date.tzinfo is not None:
                exp_date = exp_date.replace(tzinfo=None)
            delay_days = (now - exp_date).days
            if delay_days > 5:
                is_delayed = True
                issues.append(f"Shipment is {delay_days} days past expected delivery date")

    # ── Stuck Detection ──────────────────────────────────────────────────────
    if checkpoints:
        # Hub repetition check
        recent = checkpoints[:10]
        hub_counts = {}
        for cp in recent:
            hub = (cp.get("city") or cp.get("location") or cp.get("place") or "").strip().lower()
            if hub:
                hub_counts[hub] = hub_counts.get(hub, 0) + 1
        repeated_hubs = [h for h, c in hub_counts.items() if c >= 3]
        if repeated_hubs:
            is_stuck = True
            issues.append(f"Stuck at same hub: {', '.join(h.title() for h in repeated_hubs)} (≥3 events)")

        # No-movement check (48h)
        latest_date_raw = (
            checkpoints[0].get("checkpoint_time")
            or checkpoints[0].get("date")
            or checkpoints[0].get("timestamp")
            or ""
        )
        if latest_date_raw:
            latest_dt = None
            try:
                from email.utils import parsedate_to_datetime
                latest_dt = parsedate_to_datetime(str(latest_date_raw))
            except Exception:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                            "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
                    try:
                        latest_dt = datetime.datetime.strptime(str(latest_date_raw).strip(), fmt)
                        break
                    except Exception:
                        pass

            if latest_dt:
                if latest_dt.tzinfo is not None:
                    latest_dt = latest_dt.replace(tzinfo=None)
                last_movement_time = latest_dt.strftime("%Y-%m-%d %H:%M")
                hours_since = (now - latest_dt).total_seconds() / 3600
                if hours_since > 48:
                    is_stuck = True
                    issues.append(f"No movement for {int(hours_since)} hours (>48h)")

        # If no expected_delivery_date, use inactivity as delay proxy
        if not exp_del_raw and not is_delayed and last_movement_time:
            try:
                lm = datetime.datetime.strptime(last_movement_time, "%Y-%m-%d %H:%M")
                inactivity_days = (now - lm).days
                if inactivity_days > 5:
                    is_delayed = True
                    delay_days = inactivity_days
                    issues.append(f"No expected delivery date; inactive for {inactivity_days} days")
            except Exception:
                pass

    # ── Risk Detection ───────────────────────────────────────────────────────
    failed_attempts = 0
    out_for_delivery_counts = 0
    for cp in checkpoints:
        cp_tag = (cp.get("tag") or cp.get("status") or cp.get("activity") or "").lower()
        if any(kw in cp_tag for kw in ("failed", "undeliver", "delivery attempt", "not delivered")):
            failed_attempts += 1
        if any(kw in cp_tag for kw in ("out for delivery", "ofd")):
            out_for_delivery_counts += 1
            
    if failed_attempts >= 2:
        is_high_risk = True
        issues.append(f"Repeated delivery failures ({failed_attempts} attempts)")

    if out_for_delivery_counts > 1:
        issues.append(f"Repeated Out-for-Delivery scans without success ({out_for_delivery_counts} times)")

    if any(kw in current_tag for kw in ("rto", "return")):
        is_high_risk = True
        issues.append("Return/RTO process initiated")

    # Cancelled shipments
    if "cancel" in current_tag:
        is_high_risk = True
        issues.append("Shipment has been cancelled")

    # ── Status label ─────────────────────────────────────────────────────────
    if is_high_risk:
        status_label = "High Risk"
    elif is_stuck:
        status_label = "Stuck"
    elif is_delayed:
        status_label = "Delayed"
    else:
        status_label = "On-Time"

    if not issues:
        # Map known eShipz status tags to human-readable messages
        _tag_messages = {
            "inforeceived":    "Shipment information received — awaiting pickup.",
            "pickup_schedule": "Pickup scheduled — awaiting carrier collection.",
            "pickedup":        "Shipment picked up by carrier.",
            "intransit":       "Shipment is in transit.",
            "outfordelivery":  "Out for delivery.",
            "delivered":       "Shipment delivered successfully.",
            "attemptfail":     "Delivery attempt failed.",
        }
        _clean = current_tag.replace(" ", "").replace("_", "").lower()
        _msg = next((v for k, v in _tag_messages.items() if k in _clean), None)
        issues.append(_msg or "No anomalies detected — shipment is progressing normally.")

    # ── Deterministic Prediction (rule-based, NO LLM) ────────────────────
    if is_high_risk:
        prediction = "Likely to be returned"
    elif is_stuck and is_delayed:
        prediction = "Delivery at risk — may require intervention"
    elif is_stuck:
        prediction = "Delivery at risk — shipment appears stuck"
    elif is_delayed:
        prediction = "Delivery at risk — running behind schedule"
    else:
        prediction = "Will be delivered on time"

    # ── Deterministic Explanation (rule-based templates, NO LLM) ──────────
    explanation_parts = []

    if status_label == "On-Time":
        explanation_parts.append(
            f"Shipment is progressing normally. "
            f"Current carrier status: {current_tag.replace('_',' ').title()}. "
            f"{len(checkpoints)} checkpoint(s) recorded."
        )
        if last_movement_time:
            explanation_parts.append(f"Last movement: {last_movement_time}.")
    else:
        if is_delayed and delay_days > 0:
            explanation_parts.append(
                f"Shipment is delayed by {delay_days} day(s) beyond the expected delivery date."
            )
        if is_stuck and repeated_hubs:
            hub_names = ", ".join(h.title() for h in repeated_hubs)
            explanation_parts.append(
                f"Shipment appears stuck at the same hub ({hub_names}) with repeated events."
            )
        if is_stuck and not repeated_hubs:
            explanation_parts.append(
                "Shipment has shown no movement for over 48 hours."
            )
        if failed_attempts >= 2:
            explanation_parts.append(
                f"Multiple failed delivery attempts ({failed_attempts}) indicate a high risk of return (RTO)."
            )
        elif failed_attempts == 1:
            explanation_parts.append(
                "One failed delivery attempt has been recorded — monitor closely."
            )
        if any(kw in current_tag for kw in ("rto", "return")):
            explanation_parts.append(
                "A return/RTO process has been initiated by the carrier."
            )
        if len(checkpoints) == 0:
            explanation_parts.append(
                "No tracking checkpoints available yet — shipment may not have been picked up."
            )

    explanation = " ".join(explanation_parts) if explanation_parts else "No additional details available."

    return {
        "order_id": order_id,
        "awb": awb,
        "status": status_label,
        "is_delayed": is_delayed,
        "is_stuck": is_stuck,
        "is_high_risk": is_high_risk,
        "delay_days": delay_days,
        "failed_attempts": failed_attempts,
        "total_checkpoints": len(checkpoints),
        "last_movement_time": last_movement_time,
        "repeated_hubs": [h.title() for h in repeated_hubs],
        "issues": issues,
        "current_tag": current_tag,
        "prediction": prediction,
        "explanation": explanation,
    }


def bulk_scan_awb_list(awb_list: list) -> dict:
    """
    Real-time bulk scan pipeline.
    Input  : plain list of AWB / tracking ID strings.
    Flow   : for each AWB → eShipz Tracking API → _run_analysis_pure → categorize.
    Output : same shape as enrich_and_categorize_shipments.

    ❌ No SQLite.  ❌ No MongoDB.  ✅ Only live eShipz API data.
    """
    exception_ships, return_ships = [], []
    delayed_ships, stuck_ships, high_risk_ships = [], [], []
    all_analyses = []

    for raw_awb in awb_list:
        track_id = str(raw_awb).strip()
        if not track_id:
            continue

        tracking_data = _fetch_tracking_direct(track_id)

        if not tracking_data:
            # API returned nothing — mark as unavailable
            analysis = {
                "order_id": track_id, "awb": track_id,
                "status": "Data Unavailable",
                "is_delayed": False, "is_stuck": False, "is_high_risk": False,
                "delay_days": 0, "failed_attempts": 0, "total_checkpoints": 0,
                "last_movement_time": None, "repeated_hubs": [],
                "issues": ["No data returned from eShipz API — AWB may not be registered."],
                "current_tag": "",
                "prediction": "Unable to determine.",
                "explanation": "eShipz API returned no tracking data for this AWB.",
                "tracking_number": track_id,
            }
            all_analyses.append(analysis)
            continue

        # Normalise to single shipment dict
        shipment_obj = {}
        if isinstance(tracking_data, list) and tracking_data:
            shipment_obj = tracking_data[0]
        elif isinstance(tracking_data, dict):
            for k in ("data", "result", "results", "trackings", "shipments"):
                if k in tracking_data and isinstance(tracking_data[k], list) and tracking_data[k]:
                    shipment_obj = tracking_data[k][0]
                    break
            else:
                shipment_obj = tracking_data

        analysis = _run_analysis_pure(shipment_obj)
        analysis["tracking_number"] = track_id
        all_analyses.append(analysis)

        live_tag = analysis.get("current_tag", "").lower()
        is_exception = any(kw in live_tag for kw in (
            "exception", "undelivered", "failed", "delivery failed", "undeliverable"))
        is_return = any(kw in live_tag for kw in ("rto", "return", "returned"))

        if is_exception:
            exception_ships.append(analysis)
        if is_return:
            return_ships.append(analysis)
        if analysis["is_delayed"] and not is_exception and not is_return:
            delayed_ships.append(analysis)
        if analysis["is_stuck"] and not is_exception and not is_return:
            stuck_ships.append(analysis)
        if analysis["is_high_risk"]:
            high_risk_ships.append(analysis)

    return {
        "exception_shipments": exception_ships,
        "return_shipments": return_ships,
        "delayed_shipments": delayed_ships,
        "stuck_shipments": stuck_ships,
        "high_risk_shipments": high_risk_ships,
        "all_analyses": all_analyses,
        "summary": {
            "total_scanned": len(all_analyses),
            "exceptions": len(exception_ships),
            "returns": len(return_ships),
            "delayed": len(delayed_ships),
            "stuck": len(stuck_ships),
            "high_risk": len(high_risk_ships),
        },
    }


def fetch_shipments_by_date_direct(min_date: str, max_date: str, page: int = 1, limit: int = 50) -> dict:
    """
    Calls eShipz GET /api/v1/get-shipments for a date range.
    Returns {"shipments": [...], "total": int, "error": str|None}
    Zero DB dependency — pure eShipz API.
    """
    api_token = (os.getenv("ESHIPZ_API_TOKEN") or os.getenv("ESHIPZ_API_KEY") or "").strip()
    if not api_token:
        return {"shipments": [], "total": 0, "error": "No eShipz API token found in environment."}

    try:
        resp = requests.get(
            "https://app.eshipz.com/api/v1/get-shipments",
            headers={"Content-Type": "application/json", "X-API-TOKEN": api_token},
            params={"min_date": min_date, "max_date": max_date, "page": page, "limit": limit},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"shipments": [], "total": 0,
                    "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}

        data = resp.json()
        # v1 returns a plain list
        if isinstance(data, list):
            ships = data
        elif isinstance(data, dict):
            ships = (
                data.get("shipments") or data.get("data") or
                data.get("results") or data.get("result") or []
            )
            if not isinstance(ships, list):
                ships = [data] if data else []
        else:
            ships = []

        return {"shipments": ships, "total": len(ships), "error": None}

    except requests.exceptions.Timeout:
        return {"shipments": [], "total": 0, "error": "Request timed out after 30 seconds."}
    except Exception as e:
        return {"shipments": [], "total": 0, "error": str(e)}


def analyze_single_shipment(track_id: str) -> dict:
    """
    Fetch live tracking data from eShipz for a single AWB and run pure-Python analysis.
    Returns the same dict shape as _run_analysis_pure.
    On API failure, returns a minimal dict with status='On-Time' and an explanation.
    """
    tracking_data = _fetch_tracking_direct(track_id)
    if not tracking_data:
        return {
            "order_id": track_id,
            "awb": track_id,
            "status": "On-Time",
            "is_delayed": False,
            "is_stuck": False,
            "is_high_risk": False,
            "delay_days": 0,
            "failed_attempts": 0,
            "total_checkpoints": 0,
            "last_movement_time": None,
            "repeated_hubs": [],
            "issues": ["No tracking data returned from eShipz API — shipment may not be registered yet."],
            "current_tag": "",
            "prediction": "Unable to determine — no API data available.",
            "explanation": "The eShipz API returned no data for this tracking ID. Verify the AWB is correct and the shipment has been registered.",
        }

    # Normalise API response to a single shipment dict
    shipment_obj = {}
    if isinstance(tracking_data, list) and tracking_data:
        shipment_obj = tracking_data[0]
    elif isinstance(tracking_data, dict):
        for k in ("data", "result", "results", "trackings", "shipments"):
            if k in tracking_data and isinstance(tracking_data[k], list) and tracking_data[k]:
                shipment_obj = tracking_data[k][0]
                break
        else:
            shipment_obj = tracking_data

    result = _run_analysis_pure(shipment_obj)
    result["tracking_number"] = track_id
    return result


def enrich_and_categorize_shipments(shipments: list, max_enrich: int = 20) -> dict:
    """
    Bulk pipeline:
      Step 1 — SQLite provides the shipment list (AWBs + metadata).
      Step 2 — For each AWB call eShipz Tracking API (POST /trackings).
      Step 3 — Run pure-Python analysis (delay / stuck / risk).
      Step 4 — Categorize and return results.

    ❌ MongoDB is NEVER used here.
    ❌ Stored status from SQLite is NEVER used for analysis.
    """
    exception_ships = []
    return_ships = []
    delayed_ships = []
    stuck_ships = []
    high_risk_ships = []
    all_analyses = []

    for ship in shipments[:max_enrich]:
        track_id = (
            ship.get("tracking_number")
            or ship.get("awb")
            or ship.get("awb_number")
            or ship.get("track_id")
            or ""
        ).strip()

        # Fetch LIVE data from eShipz API
        enriched_ship = dict(ship)
        if track_id:
            tracking_data = _fetch_tracking_direct(track_id)
            if tracking_data:
                if isinstance(tracking_data, list) and tracking_data:
                    enriched_ship.update(tracking_data[0])
                elif isinstance(tracking_data, dict):
                    for k in ("data", "result", "results", "trackings", "shipments"):
                        if k in tracking_data and isinstance(tracking_data[k], list) and tracking_data[k]:
                            enriched_ship.update(tracking_data[k][0])
                            break
                    else:
                        enriched_ship.update(tracking_data)

        # Run pure-Python analysis on LIVE data
        analysis = _run_analysis_pure(enriched_ship)
        analysis["tracking_number"] = track_id
        all_analyses.append(analysis)

        # Categorize using LIVE status from analysis (not SQLite tag)
        live_tag = analysis.get("current_tag", "").lower()
        is_exception = any(kw in live_tag for kw in (
            "exception", "undelivered", "failed", "delivery failed", "undeliverable",
        ))
        is_return = any(kw in live_tag for kw in ("rto", "return", "returned"))

        if is_exception:
            exception_ships.append({**enriched_ship, "_analysis": analysis})
        if is_return:
            return_ships.append({**enriched_ship, "_analysis": analysis})
        if analysis["is_delayed"] and not is_exception and not is_return:
            delayed_ships.append({**enriched_ship, "_analysis": analysis})
        if analysis["is_stuck"] and not is_exception and not is_return:
            stuck_ships.append({**enriched_ship, "_analysis": analysis})
        if analysis["is_high_risk"]:
            high_risk_ships.append({**enriched_ship, "_analysis": analysis})

    return {
        "exception_shipments": exception_ships,
        "return_shipments": return_ships,
        "delayed_shipments": delayed_ships,
        "stuck_shipments": stuck_ships,
        "high_risk_shipments": high_risk_ships,
        "all_analyses": all_analyses,
        "summary": {
            "total_scanned": len(shipments[:max_enrich]),
            "exceptions": len(exception_ships),
            "returns": len(return_ships),
            "delayed": len(delayed_ships),
            "stuck": len(stuck_ships),
            "high_risk": len(high_risk_ships),
        },
    }