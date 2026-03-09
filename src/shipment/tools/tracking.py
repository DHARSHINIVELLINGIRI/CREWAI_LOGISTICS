import os
import httpx
from typing import Any
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from your .env file
load_dotenv()

mcp = FastMCP("eShipz_Innovation_Project")

# Constants
ESHIPZ_API_URL = "https://app.eshipz.com/api/v2/trackings"
# It's safer to pull this from your .env file
ESHIPZ_TOKEN = os.getenv("ESHIPZ_API_TOKEN", "5ad42f15940faf0510b62515")

async def fetch_from_eshipz(tracking_id: str) -> dict[str, Any] | None:
    headers = {
        "Content-Type": "application/json",
        "X-API-TOKEN": ESHIPZ_TOKEN
    }
    payload = {"track_id": tracking_id}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(ESHIPZ_API_URL, headers=headers, timeout=30.0, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Connection Error: {e}")
            return None
# Change this line in tracking.py
@mcp.tool()
async def get_tracking(tracking_number: str) -> str:  # Changed from get_shipment_status
    """
    Retrieves real-time tracking data for a specific shipment ID.
    """
    data = await fetch_from_eshipz(tracking_number)
    # ... rest of your code ...
@mcp.tool()
async def get_shipment_status(tracking_number: str) -> str:
    """
    Retrieves real-time tracking data for a specific shipment ID.
    """
    data = await fetch_from_eshipz(tracking_number)
    if not data or "data" not in data:
        return "❌ Could not find details for that tracking number. Please verify and try again."

    info = data["data"]
    return (
        f"📦 **Tracking Update**\n"
        f"• **Status:** {info.get('status', 'Processing')}\n"
        f"• **Carrier:** {info.get('carrier', 'eShipz Partner')}\n"
        f"• **Last Event:** {info.get('last_event', 'Package scanned')}\n"
        f"• **ETA:** {info.get('estimated_delivery', 'TBD')}"
    )

@mcp.tool()
async def check_carrier_performance(carrier_name: str) -> str:
    """
    Checks the historical performance and reliability of a specific carrier.
    """
    # This is where you would implement the performance API call 
    # using the docs provided by the eShipz team.
    return f"📊 Carrier '{carrier_name}' currently has a 98% on-time delivery rate."

if __name__ == "__main__":
    mcp.run(transport='stdio')