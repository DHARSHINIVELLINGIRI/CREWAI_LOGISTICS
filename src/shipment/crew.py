import os
from dotenv import load_dotenv
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from shipment.tools.custom_tools import LogisticsTools
from crewai_tools import SerperDevTool

load_dotenv()

@CrewBase
class EshipzOrchestrator():
    """Eshipz Logistics Orchestrator Crew"""

    # Using Gemini LLM
    gemini_llm = LLM(
        model="gemini/gemini-3-flash-preview", # Try this first
        api_key=os.getenv("GEMINI_API_KEY")
    )

    @agent
    def planning_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['planning_agent'],
            tools=[SerperDevTool()], # <--- Add this tool
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
            llm=self.gemini_llm,
            verbose=True
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