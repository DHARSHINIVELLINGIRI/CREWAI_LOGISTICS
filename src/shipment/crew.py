import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from shipment.tools.tool_serve import (
    track_shipment_eshipz, generate_barcode,
    fetch_shipments_by_date, analyze_shipment_intelligence,
)
from shipment.tools.custom_tools import LogisticsTools
from shipment.tools.tracking import (
    get_shipment_status,
    check_carrier_performance,
    predict_delivery_risk,
    analyze_route_intelligence,
    compare_carriers,
    get_customer_alert_level,
    generate_logistics_report,
)


from dotenv import load_dotenv

load_dotenv()

@CrewBase
class eShipzOrchestrator():
    """eShipz Logistics Orchestrator Crew"""

    # Change the LLM definition
   
# ✅ SWITCH TO 8B: This bypasses the 70B rate limit error immediately
    gemini_llm = LLM(
    model="groq/llama-3.3-70b-versatile", 
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.0 # ❌ CRITICAL: 0.0 stops the AI from 'inventing' search tools
) 
    @agent
    def planning_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['planning_agent'],
            llm=self.gemini_llm,
            verbose=True
        )

    @agent
    def booking_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['booking_agent'],
            tools=[LogisticsTools.awb_generator, generate_barcode],
            llm=self.gemini_llm,
            verbose=True
        )

    @agent
    def tracking_agent(self) -> Agent:
       return Agent(
            config=self.agents_config['tracking_agent'],
            tools=[track_shipment_eshipz],
            llm=self.gemini_llm,
            verbose=True
        )

    # ── NEW AGENT 4: Logistics Supervisor ─────────────────────────────────────
    @agent
    def logistics_supervisor(self) -> Agent:
        return Agent(
            config=self.agents_config['logistics_supervisor'],
            tools=[fetch_shipments_by_date],
            llm=self.gemini_llm,
            verbose=True
        )

    # ── NEW AGENT 5: Shipment Intelligence Analyst ────────────────────────────
    @agent
    def shipment_intelligence(self) -> Agent:
        return Agent(
            config=self.agents_config['shipment_intelligence'],
            tools=[analyze_shipment_intelligence],
            llm=self.gemini_llm,
            verbose=True
        )

    @task
    def carrier_selection_task(self) -> Task:
        return Task(
            config=self.tasks_config['carrier_selection_task'],
            agent=self.planning_agent() # ✅ Explicitly assign the Planning Agent
        )

    @task
    def booking_task(self) -> Task:
        return Task(
            config=self.tasks_config['booking_task'],
            agent=self.booking_agent()  # ✅ Explicitly assign the Booking Agent
        )

    @task
    def tracking_task(self) -> Task:
        return Task(
            config=self.tasks_config['tracking_task'],
            agent=self.tracking_agent() # ✅ Explicitly assign the Tracking Agent
        )

    # ── NEW TASK: Supervisor Scan (Agent 4) ───────────────────────────────────
    @task
    def supervisor_scan_task(self) -> Task:
        return Task(
            config=self.tasks_config['supervisor_scan_task'],
            agent=self.logistics_supervisor()
        )

    # ── NEW TASK: Intelligence Analysis (Agent 5) ─────────────────────────────
    @task
    def intelligence_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config['intelligence_analysis_task'],
            agent=self.shipment_intelligence()
        )

    @crew
    def crew(self) -> Crew:
       # Inside your Crew definition
        return Crew(
    agents=self.agents,
    tasks=self.tasks,
    process=Process.sequential,
    verbose=True,
    max_rpm=2  # 🚀 Add this! It limits requests to 2 per minute.
)