"""
Tracking Service — unified API for tracking shipments, predicting delays,
visualising routes, and generating AI insights.
Supports both TKT000001 and legacy SHP-XXXXXX tracking IDs.
"""

import datetime
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.simulation_engine import get_simulator
from services.delay_prediction   import predict_delay
from services.carrier_analytics  import get_analytics
from services.india_network      import INDIA_CITIES


# ── Track ──────────────────────────────────────────────────────────────────────
def track_shipment(tracking_id: str, db=None) -> dict:
    sim  = get_simulator(db=db)
    data = sim.get_shipment(tracking_id)

    if not data:
        # Try MongoDB fallback
        if db is not None:
            try:
                rec = db.shipments.find_one({"tracking_id": tracking_id})
                if rec:
                    return {
                        "tracking_id":  tracking_id,
                        "current_city": rec.get("current_city", "Unknown"),
                        "destination":  rec.get("destination", "—"),
                        "lat":          rec.get("latitude", 0),
                        "lon":          rec.get("longitude", 0),
                        "status":       rec.get("status", "Unknown"),
                        "carrier":      rec.get("carrier", "—"),
                        "eta":          rec.get("eta", "TBD"),
                        "speed_kmph":   0,
                        "progress_pct": 100 if rec.get("status") == "Delivered" else 50,
                        "source":       rec.get("origin", "—"),
                        "error":        False,
                    }
            except Exception:
                pass
        return {"error": True, "message": f"Shipment '{tracking_id}' not found. Check the tracking ID."}

    route    = data.get("route", [])
    leg      = data.get("current_leg", 0)
    progress = min(100.0, round(
        ((leg + data.get("leg_progress", 0)) / max(len(route) - 1, 1)) * 100, 1
    ))

    eta_str = "TBD"
    try:
        eta_dt  = datetime.datetime.fromisoformat(data.get("eta", ""))
        hrs     = max(0.0, (eta_dt - datetime.datetime.now()).total_seconds() / 3600)
        eta_str = f"{hrs:.1f}h ({eta_dt.strftime('%d %b %H:%M')})"
    except Exception:
        pass

    return {
        "tracking_id":  tracking_id,
        "source":       data.get("source", ""),
        "destination":  data.get("destination", ""),
        "current_city": data.get("current_city", ""),
        "lat":          round(data.get("lat", 0), 6),
        "lon":          round(data.get("lon", 0), 6),
        "status":       data.get("status", "In Transit"),
        "carrier":      data.get("carrier", ""),
        "weight":       data.get("weight", ""),
        "priority":     data.get("priority", ""),
        "speed_kmph":   round(data.get("speed_kmph", 0), 1),
        "total_distance_km": data.get("total_distance_km", 0),
        "progress_pct": progress,
        "eta":          eta_str,
        "route":        route,
        "delay_minutes":data.get("delay_minutes", 0),
        "last_updated": data.get("last_updated", "")[:19],
        "error":        False,
    }


# ── History ────────────────────────────────────────────────────────────────────
def get_tracking_history(tracking_id: str, db=None) -> dict:
    sim     = get_simulator(db=db)
    rows    = sim.get_tracking_history(tracking_id)

    events  = [
        {
            "timestamp": r.get("timestamp", ""),
            "location":  r.get("city", "—"),
            "event":     _status_to_event(r.get("status", ""), r.get("city", "")),
            "lat":       r.get("latitude",  0),
            "lon":       r.get("longitude", 0),
        }
        for r in rows
    ]

    return {
        "tracking_id": tracking_id,
        "past_events": events,
        "total_events":len(events),
        "error":       len(events) == 0 and "No history found." or False,
    }


def _status_to_event(status: str, city: str) -> str:
    if status == "Delivered":
        return f"📦 Delivered at {city}"
    elif status == "Delayed":
        return f"⚠️ Delay recorded near {city}"
    else:
        return f"📍 Arrived at {city}"


# ── Delay Prediction ──────────────────────────────────────────────────────────
def predict_shipment_delay(tracking_id: str, db=None) -> dict:
    sim  = get_simulator(db=db)
    data = sim.get_shipment(tracking_id)

    if not data:
        return {"error": True, "message": "Shipment not found."}

    result = predict_delay(
        tracking_id  = tracking_id,
        distance_km  = data.get("total_distance_km", 200),
        speed_kmph   = data.get("speed_kmph", 65),
        carrier      = data.get("carrier", "Unknown"),
        destination  = data.get("destination", "Mumbai"),
        priority     = data.get("priority", "Medium"),
    )
    result["error"]                 = False
    result["delay_probability_pct"] = f"{result['delay_probability'] * 100:.1f}%"
    return result


# ── Route Visualization ────────────────────────────────────────────────────────
def get_route_visualization(tracking_id: str, db=None) -> dict:
    from services.india_network import bfs_route
    sim  = get_simulator(db=db)
    data = sim.get_shipment(tracking_id)

    # ── Fallback to MongoDB if not in live memory ─────────────────────────────
    if not data and db is not None:
        try:
            rec = db.shipments.find_one({"tracking_id": tracking_id})
            if rec:
                data = {
                    "route":    bfs_route(
                        rec.get("origin", "Delhi"),
                        rec.get("destination", "Mumbai")
                    ),
                    "lat":  rec.get("latitude", 0),
                    "lon":  rec.get("longitude", 0),
                    "source":      rec.get("origin", "Delhi"),
                    "destination": rec.get("destination", "Mumbai"),
                }
        except Exception:
            pass

    # ── Fallback: look up in user_shipments SQLite table ─────────────────────
    if not data:
        try:
            from auth.database import get_conn
            conn = get_conn()
            row  = conn.execute(
                "SELECT source, destination FROM user_shipments WHERE tracking_id=?",
                (tracking_id,)
            ).fetchone()
            conn.close()
            if row:
                src, dst = row["source"], row["destination"]
                data = {
                    "route":       bfs_route(src, dst),
                    "lat":         INDIA_CITIES.get(src, {}).get("lat", 20),
                    "lon":         INDIA_CITIES.get(src, {}).get("lon", 78),
                    "source":      src,
                    "destination": dst,
                }
        except Exception:
            pass

    if not data:
        return {"error": True, "message": "Shipment not found in any store."}

    route        = data.get("route", [])
    route_coords = []
    for city in route:
        node = INDIA_CITIES.get(city, {})
        if node:
            route_coords.append({
                "city": city, "lat": node["lat"], "lon": node["lon"]
            })

    return {
        "tracking_id":  tracking_id,
        "route_coords": route_coords,
        "current_lat":  data.get("lat", 0),
        "current_lon":  data.get("lon", 0),
        "error":        False,
    }


# ── AI Insight ────────────────────────────────────────────────────────────────
def generate_ai_insight(tracking_id: str, db=None) -> str:
    info  = track_shipment(tracking_id, db)
    if info.get("error"):
        return f"❌ Cannot generate insight: {info.get('message')}"

    delay = predict_shipment_delay(tracking_id, db)
    prob  = delay.get("delay_probability", 0) if not delay.get("error") else 0
    risk  = delay.get("risk_level", "Low")     if not delay.get("error") else "Low"
    reason= delay.get("reason", "")            if not delay.get("error") else ""

    status   = info.get("status", "In Transit")
    city     = info.get("current_city", "—")
    dest     = info.get("destination", "—")
    carrier  = info.get("carrier", "—")
    speed    = info.get("speed_kmph", 0)
    eta      = info.get("eta", "TBD")
    progress = info.get("progress_pct", 0)
    delay_m  = info.get("delay_minutes", 0)

    risk_icon = "🟢" if risk == "Low" else "🟡" if risk == "Medium" else "🔴"

    insight = f"📍 **{tracking_id}** is currently near **{city}** → heading to **{dest}**.\n\n"
    insight += f"🚛 **{carrier}** | Status: **{status}** | Speed: {speed:.0f} km/h\n"
    insight += f"📊 Journey: **{progress:.1f}%** complete | ETA: {eta}\n\n"

    if delay_m > 0:
        insight += f"⚠️ **Delay:** +{delay_m} minutes already accumulated.\n"

    insight += f"{risk_icon} **Delay Risk:** {risk} ({prob*100:.1f}%) — {reason}\n\n"

    if status == "Delivered":
        insight += "✅ **Shipment delivered successfully!**"
    elif risk == "High":
        insight += "🔴 **Recommendation:** Contact carrier proactively. Customer notification advised."
    elif risk == "Medium":
        insight += "🟡 **Recommendation:** Monitor closely. Proactive update may improve customer experience."
    else:
        insight += "🟢 **Shipment is on track.** No action required."

    return insight
