from crewai.tools import tool
import barcode
from barcode.writer import ImageWriter
import random
import string

class LogisticsTools:
    
    @tool("generate_barcode")
    def generate_barcode(awb_number: str):
        """Generates a physical barcode image for a shipping label."""
        try:
            # Create a barcode using Code128 format
            code128 = barcode.get('code128', awb_number, writer=ImageWriter())
            filename = f"shipping_label"
            code128.save(filename)
            return f"Barcode saved successfully as {filename}.png"
        except Exception as e:
            return f"Failed to generate barcode: {str(e)}"

    @tool("awb_generator")
    def awb_generator(carrier: str):
        """Generates a unique Air Waybill number based on the carrier name."""
        prefix = carrier[:3].upper()
        digits = ''.join(random.choices(string.digits, k=10))
        return f"{prefix}-{digits}"