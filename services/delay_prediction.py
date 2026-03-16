"""
Delay Prediction Module
Heuristic / lightweight ML model for estimating shipment delay probability.
"""

import math
import random
import datetime
from typing import Dict, Any

# ── Carrier Reliability Scores (0.0 → 1.0, higher = more reliable) ──────────
CARRIER_RELIABILITY: Dict[str, float] = {
    "BlueDart":       0.95,
    "FedEx":          0.93,
    "Delhivery":      0.88,
    "DTDC":           0.82,
    "Eshipz Express": 0.90,
}

# ── Route Congestion Index (higher = more likely delay) ───────────────────────
ROUTE_CONGESTION: Dict[str, float] = {
    "Chennai":    0.75,
    "Coimbatore": 0.60,
    "Trichy":     0.45,
    "Salem":      0.40,
    "Madurai":    0.50,
    "Dindigul":   0.30,
    "Vellore":    0.35,
    "Erode":      0.25,
}

# ── Time-of-day penalty (rush hours increase delay risk) ─────────────────────
def _time_penalty() -> float:
    hour = datetime.datetime.now().hour
    if 8 <= hour <= 10 or 17 <= hour <= 20:
        return 0.15   # peak traffic
    if 0 <= hour <= 5:
        return -0.10  # night time, less congestion
    return 0.0


def _priority_factor(priority: str) -> float:
    """High priority shipments get premium lanes, reducing delay risk."""
    return {"High": -0.10, "Medium": 0.0, "Low": 0.08}.get(priority, 0.0)


def predict_delay(
    tracking_id: str,
    distance_km: float,
    speed_kmph: float,
    carrier: str,
    destination: str,
    priority: str = "Medium",
    history_delays: int = 0,
) -> Dict[str, Any]:
    """
    Returns delay prediction for a shipment.

    Parameters
    ----------
    tracking_id     : shipment ID
    distance_km     : total route distance
    speed_kmph      : current speed
    carrier         : carrier name
    destination     : destination city
    priority        : Low / Medium / High
    history_delays  : number of past delays for this carrier (0–5)

    Returns
    -------
    dict with keys: delay_probability, predicted_delay_minutes,
                    confidence_score, reason, risk_level
    """

    # Base probability from distance
    dist_factor = min(distance_km / 1500.0, 0.5)          # 0 → 0.5

    # Carrier reliability modifier (lower reliability → higher delay prob)
    reliability = CARRIER_RELIABILITY.get(carrier, 0.85)
    carrier_factor = (1.0 - reliability) * 0.6             # 0 → ~0.11

    # Congestion at destination
    congestion = ROUTE_CONGESTION.get(destination, 0.35)
    congestion_factor = congestion * 0.35                   # 0 → 0.26

    # Historical delays (each past delay adds 3 % risk)
    history_factor = min(history_delays * 0.03, 0.15)

    # Time of day
    time_factor = _time_penalty()

    # Priority lane
    priority_adj = _priority_factor(priority)

    # Raw probability
    raw_prob = (
        dist_factor +
        carrier_factor +
        congestion_factor +
        history_factor +
        time_factor +
        priority_adj +
        random.uniform(-0.03, 0.03)   # small noise
    )
    delay_prob = round(max(0.02, min(raw_prob, 0.92)), 3)

    # Predicted delay in minutes (proportional to probability and distance)
    avg_delay_min = (delay_prob * distance_km * 0.8) + random.uniform(-10, 15)
    predicted_delay_min = max(0, round(avg_delay_min))

    # Confidence score (inversely proportional to noise)
    confidence = round(random.uniform(0.72, 0.94), 2)

    # Risk level
    if delay_prob < 0.20:
        risk_level = "Low"
    elif delay_prob < 0.50:
        risk_level = "Medium"
    else:
        risk_level = "High"

    # Reason string
    reasons = []
    if congestion > 0.60:
        reasons.append(f"high congestion at {destination}")
    if reliability < 0.88:
        reasons.append(f"{carrier} reliability score is below average")
    if distance_km > 400:
        reasons.append("long-distance route")
    if history_delays > 2:
        reasons.append("carrier has recent delay history")
    if not reasons:
        reasons.append("route is clear and on schedule")

    return {
        "tracking_id":             tracking_id,
        "delay_probability":       delay_prob,
        "delay_probability_pct":   f"{delay_prob * 100:.1f}%",
        "predicted_delay_minutes": predicted_delay_min,
        "confidence_score":        confidence,
        "risk_level":              risk_level,
        "reason":                  "; ".join(reasons),
        "predicted_delivery_time": (
            datetime.datetime.now() +
            datetime.timedelta(minutes=predicted_delay_min)
        ).strftime("%Y-%m-%d %H:%M"),
    }
