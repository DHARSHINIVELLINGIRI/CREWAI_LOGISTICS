# CREWAI_LOGISTICS: Comprehensive Project Documentation

## Overview

**Eshipz AI** is an intelligent logistics and shipment management platform that combines AI-driven decision-making with real-time tracking. The project demonstrates a production-grade integration of **CrewAI**—a framework for multi-agent AI orchestration—with a full-stack logistics system.

**Core Purpose:**
- Automate three critical logistics workflow stages: **carrier selection → shipment booking → comprehensive tracking intelligence**
- Use CrewAI agents as autonomous specialists who reason about shipments and make intelligent recommendations
- Provide a unified Streamlit interface for both regular users and administrators
- Track shipments across a 24-city pan-India network using real-time simulation and predictive analytics

**Key Innovation:** Rather than using traditional rule engines, three specialized AI agents (Planning, Booking, and Tracking agents) powered by Google's Gemini 2.0 Flash collaborate to solve complex logistics decisions.

## Main Workflow & User Interaction

### High-Level User Journey

1. **LOGIN (Authentication)**: SQLite-backed auth database with role-based access (User vs Admin)
2. **DASHBOARD (User-Specific or Admin View)**: Users track shipments, admins monitor all shipments
3. **NEW SHIPMENT (Triggers CrewAI Workflow)**: User enters weight, source, destination, priority
4. **CREWAI ORCHESTRATION (Autonomous Agent Processing)**: Three agents execute sequentially
5. **SIMULATION & TRACKING**: Background thread simulates shipment movement with GPS updates every 5 seconds
6. **REAL-TIME MONITORING**: Track location, ETA, carrier performance, delay predictions

### CrewAI Workflow Sequence

The project executes a **sequential, multi-agent pipeline** defined in `src/shipment/crew.py`:

1. **Planning Agent**: Analyzes parameters and selects optimal carrier
2. **Booking Agent**: Generates AWB + barcode, confirms manifest
3. **Tracking Agent**: Produces 360° intelligence report using 7 specialized tools

## Key Features & Functionalities

### A. Carrier Intelligence & Selection
- Real-time carrier performance scoring (BlueDart, FedEx, Delhivery, DTDC, Eshipz Express)
- On-time delivery rates, average delays, reliability grades (A+, A, B+, B)
- SLA compliance tracking and breach risk assessment
- Cost-per-kg analysis and zone-based pricing optimization

### B. Shipment Documentation
- Automatic AWB (Air Waybill) generation with carrier-specific prefixes
- Code128 barcode generation for physical shipping labels
- Digital manifest creation and network validation
- Barcode scanning support across carrier networks

### C. Real-Time Tracking
- Live GPS location tracking with 24-city pan-India network coverage
- Route visualization showing GPS coordinates and city waypoints
- Current speed, distance traveled, and journey progress percentage
- ETA calculation with confidence intervals

### D. Predictive Analytics
- **Multi-factor delay prediction**: combines carrier reliability, route congestion, time-of-day traffic, priority lane eligibility
- **SLA breach risk assessment**: calculates probability of missing committed delivery dates
- **Route congestion intelligence**: identifies peak traffic hours and alternate routes
- **Confidence scoring**: provides ML model confidence for all predictions

### E. Role-Based Dashboards
- **User Dashboard**: Personal shipment tracking, history, AI assistant
- **Admin Dashboard**: Real-time India fleet map, user management, carrier analytics, bulk shipment control

### F. Advanced Analytics
- Carrier benchmarking and comparative performance analysis
- Customer alert level classification (GREEN/YELLOW/RED)
- Lifecycle stage tracking (Created → Picked Up → In Transit → Out for Delivery → Delivered)
- Shipment history with timestamped events

## Architecture & CrewAI Integration

### System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT UI LAYER                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ Auth (Login)    │  │ User Dashboard  │  │  Admin Dashboard│      │
│  │ + SQLite Auth DB│  │ Live Tracking   │  │  Fleet Map      │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
└────────────┬──────────────────────┬──────────────────┬────────────────┘
             │                      │                  │
             ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CREWAI ORCHESTRATION LAYER                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ EshipzOrchestrator (Crew).crew()                             │   │
│  │ ├─ Planning Agent   → Carrier Selection Task                 │   │
│  │ ├─ Booking Agent    → Booking & AWB Generation Task          │   │
│  │ └─ Tracking Agent   → 360° Intelligence Report Task          │   │
│  │                                                               │
│  │ Process: Sequential (agents execute one after another)        │
│  │ LLM: Google Gemini 2.0 Flash (temperature=0.7, max_iter=8)   │   │
│  │ Memory: Shared crew memory across all agents                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────┬────────────────────────────┘
             │                             │
             ▼                             ▼
┌────────────────────────┐    ┌──────────────────────────────────────┐
│ AGENT TOOLS            │    │ SERVICES LAYER                       │
│ (CrewAI Decorated)     │    │ ┌─────────────────────────────────┐  │
│ ┌──────────────────┐   │    │ │ Tracking Service               │  │
│ │ AWB Generator    │   │    │ │ ├─ track_shipment()            │  │
│ │ Barcode Gen      │   │    │ │ ├─ get_tracking_history()      │  │
│ │ Network Manifest │   │    │ │ └─ predict_shipment_delay()    │  │
│ └──────────────────┘   │    │ ├─ Simulation Engine (threading) │  │
│                        │    │ │ ├─ Background simulation loop   │  │
│                        │    │ │ └─ GPS interpolation engine    │  │
│ + 7 TRACKING TOOLS     │    │ ├─ Delay Prediction              │  │
│ ┌──────────────────┐   │    │ │ ├─ Multi-factor models         │  │
│ │ get_shipment_    │   │    │ │ ├─ Confidence scoring          │  │
│ │ status           │   │    │ │ └─ Historical averaging         │  │
│ ├─ check_carrier_ │   │    │ ├─ Carrier Analytics             │  │
│ │ performance      │   │    │ ├─ Performance metrics          │  │
│ ├─ predict_       │   │    │ │ └─ MongoDB integration          │  │
│ │ delivery_risk    │   │    │ ├─ Route Intelligence            │  │
│ ├─ analyze_route_ │   │    │ ├─ Map Visualization             │  │
│ │ intelligence     │   │    │ └─ Lifecycle Management          │  │
│ ├─ compare_       │   │    │    └─ 5-stage shipment pipeline  │  │
│ │ carriers         │   │    │                                   │  │
│ ├─ get_customer_  │   │    │ + Notifications Service          │  │
│ │ alert_level      │   │    └─────────────────────────────────┘  │
│ └─ generate_      │   │                                         │
│   logistics_      │   │                                         │
│   report          │   │                                         │
│ └──────────────────┘   │                                         │
└────────────┬───────────┘                                         │
             │                                                     │
             ▼                                                     │
┌──────────────────────────────────────────────────────────────────┐
│ DATA LAYER                                                        │
│ ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│ │ MongoDB (Cloud)      │  │ ├─ tracking_history              │  │
│ │ ├─ shipments         │  │ ├─ users (auth)                  │  │
│ │ ├─ carrier_perf      │  │ │ tkt_counter (ID generator)      │  │
│ │ ├─ notifications     │  │                                  │  │
│ │ └─ shipment_history  │  │                                  │  │
│ │                      │  │                                  │  │
│ │ (Primary source)     │  │ (Local caching & sequencing)     │  │
│ └──────────────────────┘  └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### CrewAI Deep Dive

From `src/shipment/crew.py`:

```python
@CrewBase
class EshipzOrchestrator():
    """Eshipz Logistics Orchestrator Crew"""

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

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=True,        # Shared memory across all agents
        )
```

**Key Design Decisions:**
- **Sequential Processing:** Tasks execute one after another, ensuring carrier selection completes before booking
- **Shared Memory:** Crew-level memory allows the Tracking Agent to reference Planning Agent decisions
- **Tool-Equipped Agents:** Only agents that need tools (Booking & Tracking) receive them; Planning relies on LLM reasoning
- **Gemini 2.0 Flash:** Fast reasoning model chosen for speed without sacrificing quality
- **Configuration-Driven:** Agent roles, goals, backstories defined in YAML for easy customization

## Detailed Agent Explanations

### 1. Planning Agent

**Role:** Senior Logistics Strategy & Cost Optimization Expert

**Purpose:** 
The Planning Agent is the first agent in the sequential pipeline, responsible for analyzing shipment parameters and recommending the optimal carrier based on real-time cost analysis, route efficiency, carrier SLA compliance, and delivery speed benchmarks.

**Key Features:**
- **Multi-Carrier Analysis:** Compares 5 carriers (BlueDart, FedEx, Delhivery, DTDC, Eshipz Express) simultaneously
- **Cost Optimization:** Analyzes cost-per-kg, distance zones, and service level agreements
- **Performance Benchmarking:** Evaluates historical on-time delivery rates and reliability scores
- **Priority Consideration:** Factors in shipment priority (High/Medium/Low) for SLA matching
- **Data-Driven Decisions:** Justifies choices with specific metrics and data points

**Working Logic:**
1. Receives shipment inputs: weight, source, destination, priority
2. Queries carrier performance database for real-time metrics
3. Calculates cost estimates based on distance and weight
4. Evaluates SLA compliance for the route and priority level
5. Applies business rules for carrier selection (e.g., high priority prefers fastest carrier)
6. Outputs carrier recommendation with detailed justification

**Configuration (from agents.yaml):**
```yaml
planning_agent:
  role: >
    Senior Logistics Strategy & Cost Optimization Expert
  goal: >
    Analyze all shipment parameters — weight: {weight}kg, source: {source},
    destination: {destination}, priority: {priority} — and recommend the
    optimal carrier based on real-time cost analysis, route efficiency,
    carrier SLA compliance, and delivery speed benchmarks.
  backstory: >
    You are a 15-year veteran logistics strategist at Eshipz with deep
    expertise in supply chain economics. You have personally negotiated
    carrier contracts with BlueDart, FedEx, Delhivery, and DTDC. You
    analyze cost-per-kg, distance zones, service level agreements, and
    historical on-time performance to make data-driven carrier selections.
    Your decisions save the company 18% in shipping costs annually. You
    always justify your choice with specific data points.
```

**Tools Used:** None (relies on LLM reasoning and internal knowledge)

**Output:** Carrier Selection Report with recommended carrier, cost analysis, and justification

---

### 2. Booking Agent

**Role:** Logistics Operations & Documentation Specialist

**Purpose:** 
The Booking Agent handles the operational execution of the shipment booking process. It takes the carrier selection from the Planning Agent and generates all necessary documentation including AWB numbers, barcodes, and manifest confirmations.

**Key Features:**
- **AWB Generation:** Creates unique Air Waybill numbers with carrier-specific prefixes
- **Barcode Creation:** Generates Code128 barcode images for shipping labels
- **Manifest Validation:** Confirms shipment details with carrier networks
- **Documentation Automation:** Produces all required shipping documents automatically
- **Carrier Integration:** Simulates real-world carrier booking APIs

**Working Logic:**
1. Receives carrier selection from Planning Agent
2. Generates unique AWB number using carrier prefix (e.g., "BLU-4829103847" for BlueDart)
3. Creates Code128 barcode image for physical labeling
4. Validates shipment details against carrier requirements
5. Confirms manifest status with simulated network ping
6. Outputs booking confirmation with all generated documents

**Configuration (from agents.yaml):**
```yaml
booking_agent:
  role: >
    Logistics Operations & Documentation Specialist
  goal: >
    Execute the shipment booking process by generating AWB numbers,
    creating barcode labels, and confirming manifest details with the
    selected carrier network.
  backstory: >
    You are a 12-year logistics operations veteran specializing in
    carrier integrations and documentation. You have processed over
    50,000 shipments across all major Indian carriers. You ensure
    100% accuracy in AWB generation, barcode creation, and manifest
    validation. Your meticulous attention to detail prevents costly
    shipping errors and ensures seamless carrier handoffs.
```

**Tools Used:**
- `awb_generator(carrier: str)`: Generates unique AWB with carrier prefix
- `generate_barcode(awb_number: str)`: Creates Code128 barcode image
- `network_manifest_ping(awb_number: str)`: Simulates carrier network confirmation

**Output:** Booking Confirmation Report with AWB, barcode image path, and manifest status

---

### 3. Tracking Agent

**Role:** Senior Shipment Intelligence & Risk Assessment Analyst

**Purpose:** 
The Tracking Agent is the most sophisticated agent, providing comprehensive 360° analysis of the shipment throughout its lifecycle. It uses 7 specialized tools to assess route intelligence, carrier performance, delay risks, and customer communication strategies.

**Key Features:**
- **Route Intelligence:** Analyzes corridor congestion, peak hours, alternate routes
- **Carrier Deep-Dive:** Real-time performance metrics and SLA compliance
- **Risk Assessment:** Multi-factor delay prediction with confidence scoring
- **Competitive Benchmarking:** Compares selected carrier vs all alternatives
- **Customer Communication:** Generates alert levels and messaging templates
- **Executive Reporting:** Synthesizes all data into comprehensive intelligence reports
- **Memory Continuity:** Remembers context across tool calls for coherent analysis

**Working Logic:**
The Tracking Agent executes a structured 6-step analysis process:

1. **Route Intelligence:** Calls `analyze_route_intelligence()` to assess corridor data
2. **Carrier Analysis:** Calls `check_carrier_performance()` for live metrics
3. **Risk Prediction:** Calls `predict_delivery_risk()` for delay modeling
4. **Benchmarking:** Calls `compare_carriers()` for competitive analysis
5. **Customer Strategy:** Calls `get_customer_alert_level()` for communication planning
6. **Report Synthesis:** Calls `generate_logistics_report()` for final comprehensive report

**Configuration (from agents.yaml):**
```yaml
tracking_agent:
  role: >
    Senior Shipment Intelligence & Risk Assessment Analyst
  goal: >
    Provide comprehensive 360° shipment intelligence including route analysis,
    carrier performance assessment, delay risk prediction, competitive benchmarking,
    customer alert classification, and executive reporting.
  backstory: >
    You are a 20-year logistics intelligence expert with PhD-level analytics
    experience. You have analyzed over 100,000 shipments across global supply
    chains. Your predictive models have 89% accuracy in delay forecasting.
    You provide actionable intelligence that enables proactive customer
    communication and operational excellence. Your reports drive strategic
    decisions that save millions in operational costs annually.
```

**Tools Used (7 specialized tools):**

1. **`get_shipment_status(tracking_number: str)`**: Real-time GPS, location, ETA, speed
2. **`check_carrier_performance(carrier_name: str)`**: On-time rate, reliability score, SLA details
3. **`predict_delivery_risk(carrier, destination, priority)`**: Delay probability, confidence, risk level
4. **`analyze_route_intelligence(source, destination)`**: Congestion, peak hours, alternate routes
5. **`compare_carriers(destination, weight, priority)`**: Cost differentials, performance grades
6. **`get_customer_alert_level(risk_assessment)`**: GREEN/YELLOW/RED classification, messaging
7. **`generate_logistics_report(...)`**: Comprehensive executive report synthesis

**Output:** Complete 360° Shipment Intelligence Report with all analysis findings

## Workflow Example: End-to-End Shipment Creation

**User Input:**
```
Weight: 2.5 kg
Source: Chennai
Destination: Bangalore
Priority: High
```

### Step 1: Planning Agent Execution
**Analysis:** "2.5kg, Chennai→Bangalore (500km), High priority"
**Decision:** Recommends BlueDart (fastest, most reliable for high priority)
**Output:** Carrier Selection Report

### Step 2: Booking Agent Execution
**Input:** BlueDart carrier selection
**Actions:**
- Generates AWB: "BLU-4829103847"
- Creates barcode: shipping_label.png
- Confirms manifest: Network ping successful
**Output:** Booking Confirmation

### Step 3: Tracking Agent Execution
**7-Tool Analysis:**
1. Route: Direct Chennai→Bangalore, medium congestion
2. Carrier: BlueDart 95% on-time, A+ reliability
3. Risk: 12% delay probability, LOW SLA breach risk
4. Benchmark: BlueDart fastest, FedEx comparable reliability
5. Customer: GREEN status, standard messaging
6. Report: Comprehensive 360° intelligence synthesis
**Output:** Full Intelligence Report

### Step 4: Simulation Begins
- Tracking ID: TKT000123
- Route: ["Chennai", "Vellore", "Bangalore"]
- Background thread: GPS interpolation every 5 seconds
- User sees: Live map with moving blue dot, real-time ETA updates

## Key Architectural Patterns

1. **Separation of Concerns:** UI (Streamlit) ↔ AI (CrewAI) ↔ Services (Business Logic) ↔ Data (MongoDB/SQLite)
2. **Tool-Based Agent Capability:** Only agents needing external data get tools
3. **Memory Continuity:** Crew-level shared memory for inter-agent context
4. **Background Simulation:** Threading ensures consistent real-time movement
5. **Configuration-Driven Behavior:** YAML-defined agent personas and task instructions

## Deployment & Dependencies

**Python Version:** >=3.10, <3.14

**Key Dependencies:**
- `crewai[google-genai,tools]==1.9.1` — AI orchestration framework
- `streamlit>=1.54.0` — Web UI framework
- `pymongo[srv]>=4.16.0` — Cloud database
- `langchain-google-genai>=3.2.0` — Gemini LLM integration
- `python-barcode>=0.16.1` — Barcode generation

**Environment Setup:**
```bash
pip install uv
uv pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here
export MONGODB_URI=mongodb+srv://...
streamlit run app.py
```