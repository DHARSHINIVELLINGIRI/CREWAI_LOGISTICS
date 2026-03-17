"""
Delay Prediction Module — Provides ML/Heuristic based delay predictions.
"""

import random

def predict_delay(
    tracking_id: str,
    distance_km: float,
    speed_kmph: float,
    carrier: str,
    destination: str,
    priority: str
) -> dict:
    """
    Predicts the likelihood and duration of a shipment delay.
    Returns a dictionary with probability, minutes, risk level, and reason.
    """
    base_prob = 0.05
    minutes = 0
    reason = "Normal transit conditions."
    risk = "Low"

    # Higher priority means lower chance of delay as carriers prioritize them
    if priority == "High" or priority == "Urgent":
        base_prob += 0.02
    elif priority == "Low":
        base_prob += 0.15
    else:
        base_prob += 0.08

    # Longer distances have more variables and higher chance of delay
    if distance_km > 1500:
        base_prob += 0.20
    elif distance_km > 800:
        base_prob += 0.10

    # Carrier specific weights
    if carrier in ["BlueDart", "Delhivery"]:
        base_prob -= 0.05
    elif carrier == "Eshipz Express":
        base_prob -= 0.02
    elif carrier == "FedEx":
        base_prob -= 0.03

    # Add a bit of randomness
    prob = max(0.01, min(0.95, base_prob + random.uniform(-0.05, 0.05)))

    # Calculate actual delay if it hits the probability
    if random.random() < prob:
        # Expected time is distance / speed
        expected_hours = distance_km / max(speed_kmph, 1)
        
        if prob > 0.3:
            minutes = int(expected_hours * random.uniform(0.1, 0.3) * 60)
            reason = "Traffic congestion and operational bottlenecks along the route."
            risk = "Medium"
        if prob > 0.6 or distance_km > 2000:
            minutes = int(expected_hours * random.uniform(0.2, 0.5) * 60)
            reason = "Severe weather conditions or major route disruptions."
            risk = "High"

    return {
        "delay_probability": round(prob, 2),
        "predicted_delay_minutes": max(0, minutes),
        "risk_level": risk,
        "reason": reason
    }