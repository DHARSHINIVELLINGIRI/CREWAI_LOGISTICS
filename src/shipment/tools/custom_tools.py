from crewai.tools import tool
import barcode
from barcode.writer import ImageWriter
import random
import string
import time

class LogisticsTools:
    @tool("generate_barcode")
    def generate_barcode(awb_number: str):
        """Generates a physical barcode image for a shipping label."""
        try:
            code128 = barcode.get('code128', str(awb_number), writer=ImageWriter())
            code128.save("shipping_label")
            return "Barcode saved successfully as shipping_label.png"
        except Exception as e:
            return f"Failed to generate barcode: {str(e)}"

    @tool("awb_generator")
    def awb_generator(carrier: str):
        """Generates a unique Air Waybill number based on the carrier name."""
        prefix = str(carrier)[:3].upper()
        digits = ''.join(random.choices(string.digits, k=10))
        return f"{prefix}-{digits}"
    @tool("network_manifest_ping")
    def network_manifest_ping(awb_number: str):
        """Simulates a network request to the Eshipz Global Manifest Server to check AWB status."""
        # Simulating network latency
        time.sleep(1.5) 
        
        # Mocking a JSON response from a server
        server_response = {
            "status": "success",
            "server_ip": "192.168.1.45",
            "latency": "45ms",
            "data": {
                "awb": awb_number,
                "manifest_status": "Manifested",
                "location": "Chennai Hub"
            }
        }
        return f"Network Response from {server_response['server_ip']}: {server_response['data']}"