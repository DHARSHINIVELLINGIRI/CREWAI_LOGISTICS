"""
India Logistics Network — 24 major city hubs with real GPS coordinates
and a bidirectional route graph for shipment simulation.
"""

from typing import Dict, List
import math

# ── City Hub Definitions ───────────────────────────────────────────────────────
INDIA_CITIES: Dict[str, Dict] = {
    "Delhi":          {"lat": 28.6139,  "lon": 77.2090,  "zone": "North",  "congestion": 0.80},
    "Mumbai":         {"lat": 19.0760,  "lon": 72.8777,  "zone": "West",   "congestion": 0.85},
    "Chennai":        {"lat": 13.0827,  "lon": 80.2707,  "zone": "South",  "congestion": 0.75},
    "Bangalore":      {"lat": 12.9716,  "lon": 77.5946,  "zone": "South",  "congestion": 0.78},
    "Hyderabad":      {"lat": 17.3850,  "lon": 78.4867,  "zone": "South",  "congestion": 0.72},
    "Kolkata":        {"lat": 22.5726,  "lon": 88.3639,  "zone": "East",   "congestion": 0.70},
    "Ahmedabad":      {"lat": 23.0225,  "lon": 72.5714,  "zone": "West",   "congestion": 0.65},
    "Pune":           {"lat": 18.5204,  "lon": 73.8567,  "zone": "West",   "congestion": 0.68},
    "Nagpur":         {"lat": 21.1458,  "lon": 79.0882,  "zone": "Central","congestion": 0.55},
    "Jaipur":         {"lat": 26.9124,  "lon": 75.7873,  "zone": "North",  "congestion": 0.60},
    "Lucknow":        {"lat": 26.8467,  "lon": 80.9462,  "zone": "North",  "congestion": 0.60},
    "Coimbatore":     {"lat": 11.0168,  "lon": 76.9558,  "zone": "South",  "congestion": 0.55},
    "Madurai":        {"lat":  9.9252,  "lon": 78.1198,  "zone": "South",  "congestion": 0.50},
    "Trichy":         {"lat": 10.7905,  "lon": 78.7047,  "zone": "South",  "congestion": 0.45},
    "Bhopal":         {"lat": 23.2599,  "lon": 77.4126,  "zone": "Central","congestion": 0.50},
    "Kochi":          {"lat":  9.9312,  "lon": 76.2673,  "zone": "South",  "congestion": 0.60},
    "Surat":          {"lat": 21.1702,  "lon": 72.8311,  "zone": "West",   "congestion": 0.62},
    "Patna":          {"lat": 25.5941,  "lon": 85.1376,  "zone": "East",   "congestion": 0.55},
    "Guwahati":       {"lat": 26.1445,  "lon": 91.7362,  "zone": "East",   "congestion": 0.50},
    "Chandigarh":     {"lat": 30.7333,  "lon": 76.7794,  "zone": "North",  "congestion": 0.58},
    "Indore":         {"lat": 22.7196,  "lon": 75.8577,  "zone": "Central","congestion": 0.52},
    "Bhubaneswar":    {"lat": 20.2961,  "lon": 85.8245,  "zone": "East",   "congestion": 0.48},
    "Visakhapatnam":  {"lat": 17.6868,  "lon": 83.2185,  "zone": "East",   "congestion": 0.55},
    "Varanasi":       {"lat": 25.3176,  "lon": 82.9739,  "zone": "North",  "congestion": 0.52},
}

# ── Bidirectional Route Graph ──────────────────────────────────────────────────
INDIA_ROUTES: Dict[str, List[str]] = {
    "Delhi":         ["Jaipur", "Lucknow", "Chandigarh", "Agra", "Bhopal", "Nagpur"],
    "Mumbai":        ["Pune", "Surat", "Ahmedabad", "Hyderabad", "Nagpur", "Goa"],
    "Chennai":       ["Bangalore", "Coimbatore", "Trichy", "Hyderabad", "Visakhapatnam"],
    "Bangalore":     ["Chennai", "Hyderabad", "Pune", "Coimbatore", "Kochi"],
    "Hyderabad":     ["Nagpur", "Chennai", "Bangalore", "Mumbai", "Visakhapatnam", "Bhubaneswar"],
    "Kolkata":       ["Bhubaneswar", "Patna", "Guwahati", "Varanasi"],
    "Ahmedabad":     ["Surat", "Mumbai", "Jaipur", "Indore"],
    "Pune":          ["Mumbai", "Hyderabad", "Bangalore", "Nagpur"],
    "Nagpur":        ["Hyderabad", "Bhopal", "Pune", "Bhubaneswar", "Raipur"],
    "Jaipur":        ["Delhi", "Ahmedabad", "Lucknow", "Bhopal"],
    "Lucknow":       ["Delhi", "Varanasi", "Patna", "Bhopal"],
    "Coimbatore":    ["Chennai", "Kochi", "Madurai", "Bangalore"],
    "Madurai":       ["Coimbatore", "Trichy", "Kochi", "Chennai"],
    "Trichy":        ["Chennai", "Madurai", "Coimbatore"],
    "Bhopal":        ["Delhi", "Indore", "Nagpur", "Jaipur", "Lucknow"],
    "Kochi":         ["Coimbatore", "Madurai", "Bangalore"],
    "Surat":         ["Ahmedabad", "Mumbai"],
    "Patna":         ["Lucknow", "Kolkata", "Varanasi", "Guwahati"],
    "Guwahati":      ["Kolkata", "Patna"],
    "Chandigarh":    ["Delhi"],
    "Indore":        ["Ahmedabad", "Bhopal"],
    "Bhubaneswar":   ["Kolkata", "Nagpur", "Visakhapatnam", "Hyderabad"],
    "Visakhapatnam": ["Chennai", "Hyderabad", "Bhubaneswar"],
    "Varanasi":      ["Lucknow", "Patna", "Kolkata"],
}

# Ensure all referenced cities exist in INDEX (filter to known cities)
for city in list(INDIA_ROUTES.keys()):
    INDIA_ROUTES[city] = [n for n in INDIA_ROUTES[city] if n in INDIA_CITIES]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def bfs_route(src: str, dst: str) -> List[str]:
    """BFS shortest city-hop path from src to dst."""
    if src == dst:
        return [src]
    if src not in INDIA_CITIES or dst not in INDIA_CITIES:
        return [src, dst]
    from collections import deque
    visited = {src}
    queue   = deque([[src]])
    while queue:
        path = queue.popleft()
        for nb in INDIA_ROUTES.get(path[-1], []):
            if nb == dst:
                return path + [nb]
            if nb not in visited:
                visited.add(nb)
                queue.append(path + [nb])
    return [src, dst]   # fallback if no path found


def route_distance_km(route: List[str]) -> float:
    """Total km for a city-hop route."""
    total = 0.0
    for i in range(len(route) - 1):
        c1, c2 = INDIA_CITIES.get(route[i], {}), INDIA_CITIES.get(route[i+1], {})
        if c1 and c2:
            total += haversine_km(c1["lat"], c1["lon"], c2["lat"], c2["lon"])
    return round(total, 1)
