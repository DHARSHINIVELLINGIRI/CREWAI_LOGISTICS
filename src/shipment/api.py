from fastapi import FastAPI
from pydantic import BaseModel
from shipment.crew import eShipzOrchestrator
app = FastAPI(title="Multi-Agent Shipment Intelligence Hub", description="AI Logistics API")



class TrackingRequest(BaseModel):
    tracking_id: str
@app.post("/track")
def track(request: TrackingRequest):
    # Kickoff your agent from the Swagger UI
    result = eShipzOrchestrator().crew().kickoff(inputs={'tracking_id': request.tracking_id})
    return {"ai_agent_response": result}

