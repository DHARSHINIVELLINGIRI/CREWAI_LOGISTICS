import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from shipment.tools.custom_tools import LogisticsTools
from shipment.tools.tracking import get_tracking
# Change this line in crew.py
from shipment.tools.tracking import get_shipment_status # Match the actual name
from dotenv import load_dotenv
import os

load_dotenv() # This looks for your .env file and loads the keys
@CrewBase
class EshipzOrchestrator():
    """Eshipz Logistics Orchestrator Crew"""

    # This specific naming fixes the 404 Not Found error
    gemini_llm = LLM(
        model="gemini/gemini-2.5-flash-lite",# Added 'models/' prefix
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7,
        max_retries=5,          # Automatically waits and tries again on 429 errors
        request_timeout=120
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
            tools=[get_tracking], # Add the tool here
            verbose=True,
            llm=self.gemini_llm
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
            verbose=True
        )