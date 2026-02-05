import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

def list_models():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    print("--- Available Models for your Key ---")
    try:
        # This will list every model your specific key can access
        for model in client.models.list():
            print(f"Model Name: {model.name}")
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    list_models()