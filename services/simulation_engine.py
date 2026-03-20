"""
Real-Time Shipment Simulation Engine — pan-India network.
Tracking ID format: TKT000001, TKT000002 ...
Updates every 5 seconds, stores history in SQLite + optionally MongoDB.
"""

import threading
import time
import random
import datetime
import sqlite3
import os
import sys
from typing import Dict, List, Optional, Any

# ── India network ──────────────────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.india_network import (
    INDIA_CITIES, INDIA_ROUTES, bfs_route, haversine_km, route_distance_km
)
from services.lifecycle import (
    compute_lifecycle_status,
    STAGE_CREATED, STAGE_DELIVERED, STAGE_DELAYED, STAGE_IN_TRANSIT,
    get_stage_color,
)

# Re-export for backward compat (used by tracking_service, map_visualization)
CITY_NODES   = INDIA_CITIES
ROUTE_GRAPH  = INDIA_ROUTES
_haversine_km = haversine_km

# ── SQLite for tracking history ────────────────────────────────────────────────
from auth.database import DB_PATH, get_conn

_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS tracking_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id  TEXT    NOT NULL,
    city         TEXT,
    latitude     REAL,
    longitude    REAL,
    status       TEXT,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_th_tid ON tracking_history(tracking_id);
"""

_COUNTER_TABLE = """
CREATE TABLE IF NOT EXISTS tkt_counter (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    last_n  INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO tkt_counter (id, last_n) VALUES (1, 0);
"""

def _init_tables():
    conn = get_conn()
    conn.executescript(_HISTORY_TABLE)
    conn.executescript(_COUNTER_TABLE)
    conn.commit()
    conn.close()

_init_tables()


def _next_tkt_id() -> str:
    """Thread-safe sequential TKT ID generator."""
    conn = get_conn()
    conn.execute("UPDATE tkt_counter SET last_n = last_n + 1 WHERE id = 1")
    conn.commit()
    n = conn.execute("SELECT last_n FROM tkt_counter WHERE id = 1").fetchone()[0]
    conn.close()
    return f"TKT{n:06d}"


def _save_history(tracking_id: str, city: str, lat: float, lon: float, status: str):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO tracking_history (tracking_id, city, latitude, longitude, status) VALUES (?,?,?,?,?)",
            (tracking_id, city, lat, lon, status)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Carriers ───────────────────────────────────────────────────────────────────
CARRIERS = ["BlueDart", "Delhivery", "FedEx", "DTDC", "eShipz Express"]


# ── Simulator ─────────────────────────────────────────────────────────────────
class ShipmentSimulator:
    """
    Background-thread simulation engine.
    Each shipment moves one interpolated step every tick (5s).
    """

    TICK_SECONDS  = 5      # simulation update interval
    STEPS_PER_LEG = 20     # interpolation steps between consecutive cities

    def __init__(self, db=None):
        self._db          = db
        self._lock        = threading.Lock()
        self._shipments:  Dict[str, Dict] = {}
        self._stop_event  = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def _get_closest_city(self, city_name: str) -> str:
        if city_name in INDIA_CITIES: return city_name
        
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="eshipz_logistics_app")
            location = geolocator.geocode(f"{city_name}, India")
            if not location: return "Delhi" # fallback to default if completely unfound

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

    def create_shipment(
        self,
        source: str, destination: str,
        carrier: str = "", weight: float = 1.0,
        priority: str = "Medium", user_id: int = 0
    ) -> str:
        """Create a new tracked shipment. Returns TKT tracking ID."""
        true_source = source
        true_destination = destination
        
        source = self._get_closest_city(source)
        destination = self._get_closest_city(destination)

        if not carrier:
            carrier = random.choice(CARRIERS)

        tid   = _next_tkt_id()
        route = bfs_route(source, destination)

# Fallback if route cannot be computed
        if not route or len(route) < 2:
            route = [source, destination]
        dist  = route_distance_km(route)

        # Speed varies by priority
        speed = {"High": 85, "Medium": 65, "Low": 50}.get(priority, 65)
        eta_h = (dist / speed) if speed > 0 else 24
        eta   = (datetime.datetime.now() + datetime.timedelta(hours=eta_h)).isoformat()

        start_city = INDIA_CITIES[source]
        shipment = {
            "tracking_id":         tid,
            "user_id":             user_id,
            "source":              true_source,
            "destination":         true_destination,
            "origin_city":         source,
            "destination_city":    destination,
            "route":               route,
            "current_leg":         0,
            "leg_progress":        0.0,
            "interpolation_steps": 0,
            "lat":                 start_city["lat"],
            "lon":                 start_city["lon"],
            "current_city":        source,
            "status":              STAGE_CREATED,
            "carrier":             carrier,
            "weight":              weight,
            "priority":            priority,
            "speed_kmph":          speed + random.uniform(-10, 10),
            "total_distance_km":   dist,
            "eta":                 eta,
            "last_updated":        datetime.datetime.now().isoformat(),
            "delay_minutes":       0,
            "is_delayed":          False,
            "history":             [],
        }

        with self._lock:
            self._shipments[tid] = shipment

        _save_history(tid, source, start_city["lat"], start_city["lon"], "In Transit")
        self._persist_mongo(shipment)
        return tid

    def get_shipment(self, tracking_id: str) -> Optional[Dict]:
        with self._lock:
            return dict(self._shipments.get(tracking_id, {})) or None

    def get_all_active(self) -> List[Dict]:
        with self._lock:
            return [dict(s) for s in self._shipments.values()]

    def get_tracking_history(self, tracking_id: str) -> List[Dict]:
        """Fetch from SQLite."""
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT city, latitude, longitude, status, timestamp FROM tracking_history "
                "WHERE tracking_id = ? ORDER BY timestamp ASC",
                (tracking_id,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        with self._lock:
            for s in self._shipments.values():
                st = s.get("status", "Created")
                counts[st] = counts.get(st, 0) + 1
        return counts

    def mark_delivered(self, tracking_id: str) -> bool:
        """Admin action: immediately mark a shipment as delivered."""
        with self._lock:
            s = self._shipments.get(tracking_id)
            if not s:
                return False
            dest_city = INDIA_CITIES.get(s["destination"], {})
            s["status"]       = STAGE_DELIVERED
            s["current_city"] = s["destination"]
            s["lat"]          = dest_city.get("lat", s["lat"])
            s["lon"]          = dest_city.get("lon", s["lon"])
            s["last_updated"] = datetime.datetime.now().isoformat()
        _save_history(tracking_id, s["destination"], s["lat"], s["lon"], STAGE_DELIVERED)
        self._persist_mongo(s)
        return True

    def force_delay(self, tracking_id: str, minutes: int = 30) -> bool:
        """Admin action: inject a delay into an active shipment."""
        with self._lock:
            s = self._shipments.get(tracking_id)
            if not s or s["status"] == STAGE_DELIVERED:
                return False
            s["is_delayed"]    = True
            s["delay_minutes"] = s.get("delay_minutes", 0) + minutes
            s["status"]        = STAGE_DELAYED
            eta_dt = datetime.datetime.fromisoformat(s["eta"])
            s["eta"] = (eta_dt + datetime.timedelta(minutes=minutes)).isoformat()
            s["last_updated"] = datetime.datetime.now().isoformat()
        _save_history(tracking_id, s["current_city"], s["lat"], s["lon"], STAGE_DELAYED)
        return True


    def create_shipment_from_record(self, rec: dict) -> bool:
        """
        Re-add a SQLite-persisted shipment back into the live simulator.
        Used when admin updates a shipment that isn't in live memory,
        or when restoring shipments after a server restart.
        """
        tid = rec.get("tracking_id", "")
        if not tid or tid in self._shipments:
            return False

        source      = rec.get("source", "Delhi").strip().title()
        destination = rec.get("destination", "Mumbai").strip().title()
        if source not in INDIA_CITIES:
            source = "Delhi"
        if destination not in INDIA_CITIES:
            destination = "Mumbai"

        route = bfs_route(source, destination)
        dist  = route_distance_km(route)
        carrier  = rec.get("carrier", "eShipz Express")
        priority = rec.get("priority", "Medium")
        weight   = float(rec.get("weight", 1.0))
        speed    = {"High": 85, "Medium": 65, "Low": 50}.get(priority, 65)
        start    = INDIA_CITIES[source]

        # Re-enter at a random point along the route
        import hashlib
        import random
        
        # Use a stable hash of the tracking ID to deterministically scatter shipments
        seed_val = int(hashlib.md5(tid.encode()).hexdigest(), 16)
        r = random.Random(seed_val)
        
        mid_leg = r.randint(0, max(0, len(route) - 2))
        mid_city = route[mid_leg]
        mid_node = INDIA_CITIES.get(mid_city, start)
        progress_jitter = r.uniform(0.1, 0.9)

        restored_status = rec.get("status") or STAGE_IN_TRANSIT
        if restored_status in ("Booked", "Created", None):
            restored_status = STAGE_IN_TRANSIT

        eta = (datetime.datetime.now() + datetime.timedelta(hours=dist/max(speed,1)*0.5)).isoformat()

        shipment = {
            "tracking_id":         tid,
            "user_id":             rec.get("user_id", 0),
            "source":              source,
            "destination":         destination,
            "origin_city":         source,
            "destination_city":    destination,
            "route":               route,
            "current_leg":         mid_leg,
            "leg_progress":        progress_jitter,
            "interpolation_steps": int(progress_jitter * 10),
            "lat":                 mid_node["lat"],
            "lon":                 mid_node["lon"],
            "current_city":        mid_city,
            "status":              restored_status,
            "carrier":             carrier,
            "weight":              weight,
            "priority":            priority,
            "speed_kmph":          speed,
            "total_distance_km":   dist,
            "eta":                 eta,
            "last_updated":        datetime.datetime.now().isoformat(),
            "delay_minutes":       0,
            "is_delayed":          False,
            "history":             [],
        }

        with self._lock:
            self._shipments[tid] = shipment
        return True


    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    # ── Simulation loop ────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                for tid in list(self._shipments.keys()):
                    self._tick(self._shipments[tid])
            time.sleep(self.TICK_SECONDS)

    def _tick(self, s: Dict):
        """Advance one shipment by one interpolation step."""
        if s["status"] == STAGE_DELIVERED:
            return

        # ── Admin lock: don't overwrite manually-set status ───────────────────
        locked_until = s.get("status_locked_until")
        status_locked = False
        if locked_until:
            try:
                if datetime.datetime.now() < datetime.datetime.fromisoformat(locked_until):
                    status_locked = True
                else:
                    s["status_locked_until"] = None  # lock expired
            except Exception:
                s["status_locked_until"] = None

        route = s["route"]
        leg   = s["current_leg"]

        if leg >= len(route) - 1:
            # Arrived
            dest_city = INDIA_CITIES[s["destination"]]
            s["lat"]          = dest_city["lat"]
            s["lon"]          = dest_city["lon"]
            s["status"]       = STAGE_DELIVERED
            s["current_city"] = s["destination"]
            s["last_updated"] = datetime.datetime.now().isoformat()
            _save_history(s["tracking_id"], s["destination"],
                         dest_city["lat"], dest_city["lon"], STAGE_DELIVERED)
            try:
                from services.carrier_analytics import get_analytics
                get_analytics().record_delivery(
                    s["carrier"], on_time=True, delay_min=s.get("delay_minutes", 0)
                )
            except Exception:
                pass
            return

        city_a = route[leg]
        city_b = route[leg + 1]
        ca     = INDIA_CITIES.get(city_a, {})
        cb     = INDIA_CITIES.get(city_b, {})
        if not ca or not cb:
            s["current_leg"] += 1
            return

        # Steps to traverse this leg
        d_km     = haversine_km(ca["lat"], ca["lon"], cb["lat"], cb["lon"])
        speed    = s.get("speed_kmph", 65)
        time_h   = d_km / max(speed, 1)
        total_ticks = max(1, int(time_h * 3600 / self.TICK_SECONDS))

        step = s["interpolation_steps"]
        t    = min(1.0, (step + 1) / total_ticks)

        s["lat"] = ca["lat"] + t * (cb["lat"] - ca["lat"])
        s["lon"] = ca["lon"] + t * (cb["lon"] - ca["lon"])
        s["leg_progress"]        = t
        s["interpolation_steps"] = step + 1
        s["current_city"]        = city_a if t < 0.5 else city_b
        s["last_updated"]        = datetime.datetime.now().isoformat()

        # Delay simulation (10% chance per leg start)
        if step == 0 and random.random() < 0.10:
            added = random.randint(10, 60)
            s["delay_minutes"] = s.get("delay_minutes", 0) + added
            s["is_delayed"]    = True
            eta_dt = datetime.datetime.fromisoformat(s["eta"])
            s["eta"]           = (eta_dt + datetime.timedelta(minutes=added)).isoformat()
        elif s.get("is_delayed") and step > 3:
            s["is_delayed"] = False

        # ── Compute lifecycle status from route position (unless admin locked) ─
        if not status_locked:
            s["status"] = compute_lifecycle_status(
                route        = route,
                current_leg  = leg,
                leg_progress = t,
                is_delayed   = s.get("is_delayed", False),
            )

        # Advance leg when complete
        if t >= 1.0:
            s["current_leg"]        += 1
            s["interpolation_steps"] = 0
            if not status_locked:
                new_status = compute_lifecycle_status(
                    route=route, current_leg=s["current_leg"],
                    leg_progress=0.0, is_delayed=False
                )
                _save_history(s["tracking_id"], city_b, cb["lat"], cb["lon"], new_status)

        # Speed jitter
        s["speed_kmph"] = max(30, min(120, s["speed_kmph"] + random.uniform(-3, 3)))

        # Persist to MongoDB
        self._persist_mongo(s)

    def _persist_mongo(self, s: Dict):
        """Optional MongoDB persistence."""
        if self._db is None:
            return
        try:
            self._db.shipments.update_one(
                {"tracking_id": s["tracking_id"]},
                {"$set": {
                    "tracking_id": s["tracking_id"],
                    "user_id":     s["user_id"],
                    "origin":      s["source"],
                    "destination": s["destination"],
                    "current_city":s["current_city"],
                    "latitude":    s["lat"],
                    "longitude":   s["lon"],
                    "status":      s["status"],
                    "eta":         s["eta"],
                    "carrier":     s["carrier"],
                    "last_updated":s["last_updated"],
                }},
                upsert=True
            )
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_simulator_instance: Optional[ShipmentSimulator] = None
_sim_lock = threading.Lock()


def get_simulator(db=None) -> ShipmentSimulator:
    global _simulator_instance
    with _sim_lock:
        if _simulator_instance is None:
            _simulator_instance = ShipmentSimulator(db=db)
            # 1. Seed 5 demo shipments
            _seed_demo_shipments(_simulator_instance)
            # 2. Restore ALL non-delivered user shipments from SQLite
            _restore_user_shipments(_simulator_instance)
            _simulator_instance.start()
        elif db is not None and _simulator_instance._db is None:
            _simulator_instance._db = db
    return _simulator_instance


def _seed_demo_shipments(sim: ShipmentSimulator):
    """Create 5 diverse demo shipments across India."""
    demo = [
        ("Delhi",       "Mumbai",       "BlueDart",       2.5,  "High"),
        ("Chennai",     "Kolkata",      "Delhivery",      5.0,  "Medium"),
        ("Bangalore",   "Hyderabad",    "FedEx",          1.2,  "Low"),
        ("Ahmedabad",   "Lucknow",      "DTDC",           8.0,  "Medium"),
        ("Kochi",       "Guwahati",     "eShipz Express", 3.0,  "High"),
    ]
    for src, dst, carrier, wt, pri in demo:
        try:
            sim.create_shipment(source=src, destination=dst,
                                carrier=carrier, weight=wt, priority=pri)
        except Exception:
            pass


def _restore_user_shipments(sim: ShipmentSimulator):
    """Load all non-delivered user shipments from SQLite into the live simulator."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT tracking_id, user_id, source, destination, weight, priority, carrier, status "
            "FROM user_shipments WHERE status NOT IN ('Delivered','Cancelled') "
            "ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        conn.close()
        for row in rows:
            try:
                sim.create_shipment_from_record(dict(row))
            except Exception:
                pass
    except Exception:
        pass