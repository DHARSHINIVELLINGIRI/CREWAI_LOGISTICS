import requests
import json
import barcode
from barcode.writer import ImageWriter
import random
import string
import time
import os
from crewai.tools import tool

class LogisticsTools:
    
    @tool("track_shipment_eshipz")
    def track_shipment_eshipz(track_id: str):
        """Fetches real-time tracking data from the eShipz V2 API using a dynamic Tracking ID."""
        url = "https://app.eshipz.com/api/v2/trackings"
        headers = {
            "Content-Type": "application/json",
            "X-API-TOKEN": "5ad42f15940faf0510b62515" # Replace with env variable for extra security
        }
        
        # Following mentor's advice: No carrier_id, only track_id for auto-detect
        payload = {
            "track_id": str(track_id),
            "include_split": True
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # If API returns [], we return a clear status instead of crashing
                if not data or (isinstance(data, dict) and data.get("Count") == 0):
                    return f"Status for {track_id}: Integration Successful. Server response: [No active carrier records found]."
                return json.dumps(data)
            else:
                return f"Server Error: {response.status_code}. Connection to eShipz gateway failed."
        except Exception as e:
            return f"Network Exception: {str(e)}"

    @tool("generate_barcode")
    def generate_barcode(awb_number: str):
        """Generates a physical barcode image for a shipping label and uploads to AWS S3."""
        try:
            code128 = barcode.get('code128', str(awb_number), writer=ImageWriter())
            filename = f"shipping_label_{awb_number}"
            # Save locally first
            file_path = f"{filename}.png"
            code128.save(filename)
            
            # S3 Upload logic (Uses Environment Variables - No Hardcoding)
            import boto3
            s3 = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'ap-south-1')
            )
            bucket_name = os.getenv('AWS_S3_BUCKET', 'eshipz-barcodes')
            
            s3.upload_file(file_path, bucket_name, file_path)
            url = f"https://{bucket_name}.s3.{os.getenv('AWS_REGION', 'ap-south-1')}.amazonaws.com/{file_path}"
            
            return f"Success: Barcode generated and synced to Cloud Storage: {url}"
        except Exception as e:
            return f"Local Barcode generated but S3 Sync failed: {str(e)}"

    @tool("awb_generator")
    def awb_generator(carrier: str):
        """Generates a unique Air Waybill number based on the carrier name dynamically."""
        prefix = str(carrier)[:3].upper()
        digits = ''.join(random.choices(string.digits, k=10))
        return f"{prefix}-{digits}"