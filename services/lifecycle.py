"""
Shipment Lifecycle Engine
Defines the 5 canonical stages and provides status computation
based on a shipment's position within its route.

Stages:
  CREATED         → Shipment booked, awaiting pickup
  PICKED_UP       → Collected from origin warehouse
  IN_TRANSIT      → Moving between hubs
  OUT_FOR_DELIVERY→ Reached destination city, last-mile delivery
  DELIVERED       → Confirmed delivery
"""

from typing import List, Dict, Optional

# ── Stage constants ────────────────────────────────────────────────────────────
STAGE_CREATED          = "Created"
STAGE_PICKED_UP        = "Picked Up"
STAGE_IN_TRANSIT       = "In Transit"
STAGE_OUT_FOR_DELIVERY = "Out for Delivery"
STAGE_DELIVERED        = "Delivered"
STAGE_DELAYED          = "Delayed"

# Ordered pipeline (not including Delayed which is a modifier)
LIFECYCLE_STAGES = [
    STAGE_CREATED,
    STAGE_PICKED_UP,
    STAGE_IN_TRANSIT,
    STAGE_OUT_FOR_DELIVERY,
    STAGE_DELIVERED,
]

# ── Visual config ──────────────────────────────────────────────────────────────
STAGE_CONFIG = {
    STAGE_CREATED:          {"icon": "📝", "color": "#818CF8", "map_color": "#818CF8"},
    STAGE_PICKED_UP:        {"icon": "📦", "color": "#F59E0B", "map_color": "#F59E0B"},
    STAGE_IN_TRANSIT:       {"icon": "🚚", "color": "#00D1FF", "map_color": "#00D1FF"},
    STAGE_OUT_FOR_DELIVERY: {"icon": "🏠", "color": "#FB923C", "map_color": "#FB923C"},
    STAGE_DELIVERED:        {"icon": "✅", "color": "#22C55E", "map_color": "#22C55E"},
    STAGE_DELAYED:          {"icon": "⚠️", "color": "#EF4444", "map_color": "#EF4444"},
}


def compute_lifecycle_status(
    route: List[str],
    current_leg: int,
    leg_progress: float,
    is_delayed: bool = False,
    manual_status: Optional[str] = None,
) -> str:
    """
    Determine the correct lifecycle stage based on route position.

    Rules:
      leg 0 + progress < 0.5  → PICKED_UP  (leaving origin)
      leg 0 + progress >= 0.5 → IN_TRANSIT
      any middle leg           → IN_TRANSIT
      last leg + progress < 0.5 → IN_TRANSIT
      last leg + progress >= 0.5 → OUT_FOR_DELIVERY
      all legs done            → DELIVERED
    """
    if manual_status in (STAGE_DELIVERED, STAGE_CREATED, STAGE_PICKED_UP):
        return manual_status

    n_legs = max(len(route) - 1, 1)

    if current_leg >= n_legs:
        return STAGE_DELIVERED

    is_first_leg = (current_leg == 0)
    is_last_leg  = (current_leg == n_legs - 1)

    if is_first_leg:
        status = STAGE_PICKED_UP if leg_progress < 0.4 else STAGE_IN_TRANSIT
    elif is_last_leg:
        status = STAGE_OUT_FOR_DELIVERY if leg_progress >= 0.6 else STAGE_IN_TRANSIT
    else:
        status = STAGE_IN_TRANSIT

    if is_delayed:
        return STAGE_DELAYED

    return status


def stage_to_percentage(status: str) -> int:
    """Return approximate journey % for each stage (for UI progress bars)."""
    mapping = {
        STAGE_CREATED:           0,
        STAGE_PICKED_UP:        15,
        STAGE_IN_TRANSIT:       50,
        STAGE_OUT_FOR_DELIVERY: 85,
        STAGE_DELIVERED:       100,
        STAGE_DELAYED:          50,
    }
    return mapping.get(status, 0)


def format_timeline_event(status: str, city: str, timestamp: str) -> Dict:
    """Format a tracking history row into a rich timeline event."""
    cfg = STAGE_CONFIG.get(status, {"icon": "📍", "color": "#94A3B8"})
    return {
        "icon":      cfg["icon"],
        "status":    status,
        "color":     cfg["color"],
        "city":      city,
        "timestamp": timestamp[:19],
        "label":     _status_to_label(status, city),
    }


def _status_to_label(status: str, city: str) -> str:
    labels = {
        STAGE_CREATED:           f"Order confirmed — awaiting pickup at {city}",
        STAGE_PICKED_UP:         f"Picked up from {city} warehouse",
        STAGE_IN_TRANSIT:        f"In transit — passing through {city}",
        STAGE_OUT_FOR_DELIVERY:  f"Out for delivery in {city}",
        STAGE_DELIVERED:         f"Delivered at {city} ✅",
        STAGE_DELAYED:           f"Delay recorded near {city} ⚠️",
    }
    return labels.get(status, f"Update at {city}")


def get_stage_color(status: str) -> str:
    return STAGE_CONFIG.get(status, {"map_color": "#94A3B8"})["map_color"]


def get_stage_icon(status: str) -> str:
    return STAGE_CONFIG.get(status, {"icon": "📍"})["icon"]
