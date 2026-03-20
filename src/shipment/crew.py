import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
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

    gemini_llm = LLM(
        model="gemini/gemini-2.0-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7,
        max_retries=8,
        request_timeout=180,
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
            tools=[LogisticsTools.awb_generator, LogisticsTools.generate_barcode],
            llm=self.gemini_llm,
            verbose=True
        )

    @agent
    def tracking_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['tracking_agent'],
            # 7 advanced specialized tools
            tools=[
                get_shipment_status,
                check_carrier_performance,
                predict_delivery_risk,
                analyze_route_intelligence,
                compare_carriers,
                get_customer_alert_level,
                generate_logistics_report,
            ],
            llm=self.gemini_llm,
            verbose=True,
            max_iter=8,         # Allow more reasoning iterations
            memory=True,        # Remember context across tool calls
        )

    @task
    def carrier_selection_task(self) -> Task:
        return Task(config=self.tasks_config['carrier_selection_task'])

    @task
    def booking_task(self) -> Task:
        return Task(config=self.tasks_config['booking_task'])

    @task
    def tracking_task(self) -> Task:
        return Task(config=self.tasks_config['tracking_task'])

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=True,        # Shared memory across all agents
        )