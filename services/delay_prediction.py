"""
India Logistics Network — 24 major city hubs with real GPS coordinates
and a bidirectional route graph for shipment simulation.
"""

from typing import Dict, List
import math

# ── City Hub Definitions ───────────────────────────────────────────────────────
INDIA_CITIES = {

    # North
    "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794},
    "Jaipur": {"lat": 26.9124, "lon": 75.7873},
    "Lucknow": {"lat": 26.8467, "lon": 80.9462},
    "Kanpur": {"lat": 26.4499, "lon": 80.3319},
    "Agra": {"lat": 27.1767, "lon": 78.0081},
    "Varanasi": {"lat": 25.3176, "lon": 82.9739},
    "Dehradun": {"lat": 30.3165, "lon": 78.0322},

    # West
    "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Pune": {"lat": 18.5204, "lon": 73.8567},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "Surat": {"lat": 21.1702, "lon": 72.8311},
    "Rajkot": {"lat": 22.3039, "lon": 70.8022},

    # Central
    "Nagpur": {"lat": 21.1458, "lon": 79.0882},
    "Indore": {"lat": 22.7196, "lon": 75.8577},
    "Bhopal": {"lat": 23.2599, "lon": 77.4126},
    "Raipur": {"lat": 21.2514, "lon": 81.6296},

    # East
    "Kolkata": {"lat": 22.5726, "lon": 88.3639},
    "Patna": {"lat": 25.5941, "lon": 85.1376},
    "Ranchi": {"lat": 23.3441, "lon": 85.3096},
    "Bhubaneswar": {"lat": 20.2961, "lon": 85.8245},

    # North East
    "Guwahati": {"lat": 26.1445, "lon": 91.7362},

    # South
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "Coimbatore": {"lat": 11.0168, "lon": 76.9558},
    "Madurai": {"lat": 9.9252, "lon": 78.1198},
    "Kochi": {"lat": 9.9312, "lon": 76.2673},
    "Thiruvananthapuram": {"lat": 8.5241, "lon": 76.9366},
    "Mysore": {"lat": 12.2958, "lon": 76.6394},
    "Trichy": {"lat": 10.7905, "lon": 78.7047},

    # Andhra / Telangana
    "Vijayawada": {"lat": 16.5062, "lon": 80.6480},
    "Amaravati": {"lat": 16.5417, "lon": 80.5150},
    "Visakhapatnam": {"lat": 17.6868, "lon": 83.2185},

    # Others
    "Goa": {"lat": 15.2993, "lon": 74.1240},
    "Mangalore": {"lat": 12.9141, "lon": 74.8560},
}


# ─────────────────────────────────────────────
# Logistics network connections
# ─────────────────────────────────────────────
INDIA_ROUTES = {

    "Delhi": ["Jaipur", "Agra", "Lucknow", "Chandigarh"],
    "Jaipur": ["Delhi", "Ahmedabad"],
    "Agra": ["Delhi", "Lucknow"],
    "Lucknow": ["Agra", "Kanpur", "Varanasi", "Patna"],
    "Kanpur": ["Lucknow"],
    "Varanasi": ["Lucknow", "Patna", "Ranchi"],
    "Patna": ["Lucknow", "Varanasi", "Ranchi"],
    "Ranchi": ["Patna", "Kolkata"],
    "Kolkata": ["Ranchi", "Bhubaneswar", "Guwahati"],
    "Bhubaneswar": ["Kolkata", "Raipur"],
    "Guwahati": ["Kolkata"],

    "Ahmedabad": ["Jaipur", "Surat", "Indore"],
    "Surat": ["Ahmedabad", "Mumbai"],
    "Mumbai": ["Surat", "Pune", "Goa"],
    "Pune": ["Mumbai", "Hyderabad"],
    "Goa": ["Mumbai", "Mangalore"],
    "Mangalore": ["Goa", "Bangalore"],
    "Bangalore": ["Mangalore", "Mysore", "Hyderabad", "Chennai", "Coimbatore"],
    "Mysore": ["Bangalore"],
    "Hyderabad": ["Pune", "Bangalore", "Nagpur", "Vijayawada"],
    "Nagpur": ["Hyderabad", "Bhopal", "Raipur"],
    "Bhopal": ["Nagpur", "Indore"],
    "Indore": ["Bhopal", "Ahmedabad"],
    "Raipur": ["Nagpur", "Bhubaneswar"],
    "Vijayawada": ["Hyderabad", "Amaravati", "Chennai"],
    "Amaravati": ["Vijayawada"],
    "Chennai": ["Vijayawada", "Bangalore", "Trichy"],
    "Trichy": ["Chennai", "Madurai", "Coimbatore"],
    "Madurai": ["Trichy", "Thiruvananthapuram"],
    "Coimbatore": ["Bangalore", "Trichy", "Kochi"],
    "Kochi": ["Coimbatore", "Thiruvananthapuram"],
    "Thiruvananthapuram": ["Kochi", "Madurai"],
    "Visakhapatnam": ["Vijayawada"],
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
# Ensure bidirectional connectivity
for city, neighbors in list(INDIA_ROUTES.items()):
    for n in neighbors:
        INDIA_ROUTES.setdefault(n, [])
        if city not in INDIA_ROUTES[n]:
            INDIA_ROUTES[n].append(city)