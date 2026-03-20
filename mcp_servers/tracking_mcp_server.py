"""
Tracking MCP Server — follows the FastMCP pattern from the MCP docs.
https://modelcontextprotocol.io/docs/getting-started/intro

Run standalone:
    uv run python mcp_servers/tracking_mcp_server.py

This server is COMPLETELY SEPARATE from the CrewAI tools.
CrewAI agents use src/shipment/tools/tracking.py (@tool decorated).
This MCP server is for external LLM clients (Claude, ChatGPT, Cursor, etc.)
that support the Model Context Protocol.

Architecture:
    External LLM (MCP Client)
         ↓  MCP protocol (stdio / SSE)
    tracking_mcp_server.py   ← YOU ARE HERE
         ↓  Python calls
    services/tracking_service.py
         ↓
    services/simulation_engine.py  +  eShipz REST API
"""

import sys
import os

# Ensure project root is on path when run standalone
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

# ── Boot the simulation engine so tracking data exists ───────────────────────
from services.simulation_engine import get_simulator
_sim = get_simulator()   # starts background thread

# ── Import service functions ──────────────────────────────────────────────────
from services.tracking_service import (
    track_shipment,
    get_tracking_history,
    predict_shipment_delay,
    get_route_visualization,
    generate_ai_insight,
)
from services.carrier_analytics import get_analytics

# ── Create the MCP server ─────────────────────────────────────────────────────
mcp = FastMCP("eShipzLogisticsTracker")


# ── Tool 1: track_shipment ────────────────────────────────────────────────────
@mcp.tool()
def track_shipment_tool(tracking_id: str) -> dict:
    """
    Track a shipment in real-time using its SHP-XXXXXX tracking ID.

    Returns current status, city, GPS coordinates, speed, and ETA.
    All data comes from the live simulation engine — never fabricated.

    Args:
        tracking_id: The shipment tracking ID, e.g. 'SHP-123456'
    """
    return track_shipment(tracking_id)


# ── Tool 2: get_tracking_history ──────────────────────────────────────────────
@mcp.tool()
def get_tracking_history_tool(tracking_id: str) -> dict:
    """
    Retrieve the full movement history of a shipment.

    Returns the route path (list of cities), GPS coordinates for each waypoint,
    and timestamped events (e.g. 'Arrived at Salem', 'Delivered').

    Args:
        tracking_id: The shipment tracking ID, e.g. 'SHP-123456'
    """
    return get_tracking_history(tracking_id)


# ── Tool 3: predict_delay ─────────────────────────────────────────────────────
@mcp.tool()
def predict_delay_tool(tracking_id: str) -> dict:
    """
    Predict delay probability and magnitude for a shipment.

    Uses a heuristic model based on distance, carrier reliability,
    destination congestion, and time of day.

    Returns:
        delay_probability (0.0-1.0), predicted_delay_minutes,
        confidence_score, risk_level (Low/Medium/High), reason.

    Args:
        tracking_id: The shipment tracking ID, e.g. 'SHP-123456'
    """
    return predict_shipment_delay(tracking_id)


# ── Tool 4: get_route_visualization ──────────────────────────────────────────
@mcp.tool()
def get_route_visualization_tool(tracking_id: str) -> dict:
    """
    Get GPS coordinate data for rendering the shipment route on a map.

    Returns route_coords (list of {city, lat, lon}),
    plus the current vehicle position (current_lat, current_lon).

    Args:
        tracking_id: The shipment tracking ID, e.g. 'SHP-123456'
    """
    return get_route_visualization(tracking_id)


# ── Tool 5: get_carrier_performance ──────────────────────────────────────────
@mcp.tool()
def get_carrier_performance_tool(carrier_name: str = "") -> dict:
    """
    Get performance metrics for one or all carriers.

    Args:
        carrier_name: Optional. Carrier name like 'BlueDart', 'FedEx',
                      'Delhivery', 'DTDC', 'eShipz Express'.
                      If empty, returns all carriers.

    Returns:
        on_time_rate (%), average_delay_min, reliability_score, total_shipments.
    """
    analytics = get_analytics()
    if carrier_name:
        rec = analytics.get_carrier(carrier_name)
        return rec if rec else {"error": f"Carrier '{carrier_name}' not found"}
    return {"carriers": analytics.get_all()}


# ── Tool 6: generate_ai_insight ───────────────────────────────────────────────
@mcp.tool()
def generate_ai_insight_tool(tracking_id: str) -> str:
    """
    Generate a natural-language AI insight about a shipment's current state.

    Example output:
        '📍 Shipment SHP-123456 is moving from Trichy toward Salem.
         🚚 Status: In Transit | Speed: 68 km/h
         ⏱ Estimated delivery in ~2.3 hours.
         ⚠️ Delay probability: 18.5% (Risk: Low) — route is clear.'

    Data is always sourced from real tracking records — never fabricated.

    Args:
        tracking_id: The shipment tracking ID, e.g. 'SHP-123456'
    """
    return generate_ai_insight(tracking_id)


# ── Tool 7: list_active_shipments ────────────────────────────────────────────
@mcp.tool()
def list_active_shipments_tool() -> dict:
    """
    List all currently active shipments being tracked by the simulation engine.

    Returns a list of shipments with their tracking IDs, status,
    current location, carrier, source and destination.
    """
    sim = get_simulator()
    all_ships = sim.get_all_active()
    return {
        "total": len(all_ships),
        "shipments": [
            {
                "tracking_id": s.get("tracking_id"),
                "status":      s.get("status"),
                "carrier":     s.get("carrier"),
                "source":      s.get("source"),
                "destination": s.get("destination"),
                "current_leg": s.get("current_leg"),
                "route":       s.get("route", []),
            }
            for s in all_ships
        ]
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 eShipzLogisticsTracker MCP Server starting...")
    print("   Transport: stdio")
    print("   Tools: track_shipment, get_tracking_history, predict_delay,")
    print("          get_route_visualization, get_carrier_performance,")
    print("          generate_ai_insight, list_active_shipments")
    mcp.run(transport="stdio")
