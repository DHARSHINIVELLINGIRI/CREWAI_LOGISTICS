from crewai.tools import tool
import barcode
from barcode.writer import ImageWriter
import random
import string
import time

class LogisticsTools:
    @tool("generate_barcode")
    def generate_barcode(awb_number: str):
        """Generates a physical barcode image for a shipping label and uploads to AWS S3."""
        try:
            code128 = barcode.get('code128', str(awb_number), writer=ImageWriter())
            filename = f"shipping_label_{awb_number}"
            code128.save(filename)
            
            import boto3
            import os
            s3 = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'ap-south-1')
            )
            bucket_name = os.getenv('AWS_S3_BUCKET', 'eshipz-barcodes')
            file_path = f"{filename}.png"
            s3.upload_file(file_path, bucket_name, file_path)
            url = f"https://{bucket_name}.s3.{os.getenv('AWS_REGION', 'ap-south-1')}.amazonaws.com/{file_path}"
            
            return f"Barcode saved and uploaded to S3 successfully: {url}"
        except Exception as e:
            return f"Failed to generate and upload barcode: {str(e)}"

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