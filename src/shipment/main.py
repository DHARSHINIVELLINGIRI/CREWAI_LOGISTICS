#!/usr/bin/env python
import sys
import os
import json
import warnings
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Crew, Process, Task, LLM
from shipment.crew import eShipzOrchestrator

# Standard warning ignore
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# ── PRE-FLIGHT CHECK ─────────────────────────────────────────────────────────
# __file__ = src/shipment/main.py  →  parents[2] = project root  (3 levels up)
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ROOT_ENV, override=True)
print(f"[main] .env loaded from: {_ROOT_ENV} (exists={_ROOT_ENV.exists()})")


def _get_llm():
    """Return an LLM instance matching the orchestrator's config."""
    return LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.0,
    )


def run(tracking_id=None):
    """
    Run the crew with a real tracking ID. 
    Returns the FULL CrewOutput object for the UI renderer.
    """
    
    # 1. Validation: Use the Port Blair ID as a default for your demo if none provided
    if not tracking_id:
        tracking_id = "80970274836" 

    # 2. Prepare Inputs
    # We pass the tracking_id specifically so the 'eShipz Expert' knows what to track.
    inputs = {
        'tracking_id': str(tracking_id),
        'weight': '2.5',
        'destination': 'Port Blair, India', # Match your test data
        'priority': 'High'
    }
    
    print(f"🚀 AI Assistant Launching: Tracking {tracking_id}...")

    try:
        # 3. Kickoff the Orchestrator
        # This returns a CrewOutput object containing all task results + JSON
        result = eShipzOrchestrator().crew().kickoff(inputs=inputs)
        
        # 4. RETURN the full object (needed for tracking_renderer.py)
        return result

    except Exception as e:
        return f"Orchestration Error: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Supervisor Scan (Agent 4) — Bulk date-range monitoring
# ══════════════════════════════════════════════════════════════════════════════

def run_supervisor_scan(min_date: str, max_date: str):
    """
    Run Agent 4 (Logistics Supervisor) to fetch and filter shipments
    by date range into exception and return categories.
    Returns the CrewOutput object.
    """
    from shipment.tools.tool_serve import fetch_shipments_by_date

    orchestrator = eShipzOrchestrator()
    llm = _get_llm()

    supervisor = Agent(
        config=orchestrator.agents_config['logistics_supervisor'],
        tools=[fetch_shipments_by_date],
        llm=llm,
        verbose=True,
    )

    scan_task = Task(
        config=orchestrator.tasks_config['supervisor_scan_task'],
        agent=supervisor,
    )

    mini_crew = Crew(
        agents=[supervisor],
        tasks=[scan_task],
        process=Process.sequential,
        verbose=True,
        max_rpm=2,
    )

    print(f"📊 Supervisor Scan: {min_date} → {max_date}")
    result = mini_crew.kickoff(inputs={
        'min_date': min_date,
        'max_date': max_date,
    })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Intelligence Analysis (Agent 5) — Deep per-shipment analysis
# ══════════════════════════════════════════════════════════════════════════════

def run_intelligence_analysis(shipment_data: str):
    """
    Run Agent 5 (Shipment Intelligence Analyst) on a single shipment.
    shipment_data: JSON string of the shipment object.
    Returns the CrewOutput object.
    """
    from shipment.tools.tool_serve import analyze_shipment_intelligence

    orchestrator = eShipzOrchestrator()
    llm = _get_llm()

    analyst = Agent(
        config=orchestrator.agents_config['shipment_intelligence'],
        tools=[analyze_shipment_intelligence],
        llm=llm,
        verbose=True,
    )

    analysis_task = Task(
        config=orchestrator.tasks_config['intelligence_analysis_task'],
        agent=analyst,
    )

    mini_crew = Crew(
        agents=[analyst],
        tasks=[analysis_task],
        process=Process.sequential,
        verbose=True,
        max_rpm=2,
    )

    print(f"🔍 Intelligence Analysis: processing shipment data...")
    result = mini_crew.kickoff(inputs={
        'shipment_data': shipment_data,
    })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Full Intelligence Pipeline — Supervisor + Intelligence chained
# ══════════════════════════════════════════════════════════════════════════════

def run_full_intelligence_pipeline(min_date: str, max_date: str):
    """
    Full pipeline: Supervisor fetches + filters → Intelligence analyzes each.
    Returns dict with scan_result, analyses list, and summary.
    """
    print(f"🧠 Full Intelligence Pipeline: {min_date} → {max_date}")

    # Step 1: Supervisor scan
    scan_result = run_supervisor_scan(min_date, max_date)
    scan_raw = scan_result.raw if hasattr(scan_result, 'raw') else str(scan_result)

    # Step 2: Try to extract flagged shipments for deep analysis
    analyses = []
    try:
        # Try to parse the supervisor's output as JSON
        scan_data = None
        for start_char in ("{", "["):
            idx = scan_raw.find(start_char)
            if idx != -1:
                try:
                    scan_data = json.loads(scan_raw[idx:])
                    break
                except json.JSONDecodeError:
                    pass

        if scan_data:
            flagged = []
            if isinstance(scan_data, dict):
                flagged.extend(scan_data.get("exception_shipments", []))
                flagged.extend(scan_data.get("return_shipments", []))
            elif isinstance(scan_data, list):
                flagged = scan_data

            # Run intelligence analysis on each flagged shipment (max 10)
            for ship in flagged[:10]:
                try:
                    ship_json = json.dumps(ship) if isinstance(ship, dict) else str(ship)
                    analysis = run_intelligence_analysis(ship_json)
                    analyses.append({
                        "shipment": ship,
                        "analysis_raw": analysis.raw if hasattr(analysis, 'raw') else str(analysis),
                    })
                except Exception as e:
                    analyses.append({
                        "shipment": ship,
                        "analysis_raw": f"Analysis error: {str(e)}",
                    })
    except Exception as e:
        print(f"⚠️ Pipeline analysis phase error: {e}")

    return {
        "scan_raw": scan_raw,
        "analyses": analyses,
        "summary": {
            "date_range": f"{min_date} to {max_date}",
            "flagged_count": len(analyses),
        },
    }


if __name__ == "__main__":
    # If running from terminal, print the result
    final_output = run()
    print("\n--- FINAL AGENT REPORT ---")
    print(final_output)