import sys
import os
import certifi # <-- Add this import
# Get the path to the 'src' directory
src_path = os.path.join(os.path.dirname(__file__), 'src')

# Add 'src' to the system path if it's not already there
if src_path not in sys.path:
    sys.path.append(src_path)

# NOW you can safely import your crew logic
from shipment.crew import EshipzOrchestrator
import streamlit as st
import pandas as pd
import os
import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
from src.utils import apply_custom_css, load_lottie_file
from streamlit_lottie import st_lottie
from streamlit_option_menu import option_menu

# MUST be first
st.set_page_config(page_title="Eshipz AI", layout="wide")

# Apply your professional CSS file
apply_custom_css()

# Use your animations
lottie_truck = load_lottie_file("assets/animations/truck.json")
# Import your CrewAI logic
# Note: Ensure 'src' is in your PYTHONPATH or use the sys.path.append fix
try:
    from shipment.crew import EshipzOrchestrator
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
    from shipment.crew import EshipzOrchestrator

load_dotenv()

# --- 1. MONGODB CONNECTION ---





@st.cache_resource
def get_db():
    try:
        client = MongoClient(
            os.getenv("MONGODB_URI"), 
            tls=True,                           # Ensure TLS is on
            tlsAllowInvalidCertificates=True,   # THE FIX: Bypasses the handshake alert
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        client.admin.command('ping') 
        return client.shipment_db
    except Exception as e:
        st.error(f"MongoDB Connection Failed: {e}")
        return None
db = get_db()

# --- 2. SIDEBAR NAVIGATION ---
st_lottie(lottie_truck, height=150, key="truck_anim")
st.sidebar.title("🚚 Eshipz AI Logistics")
st.sidebar.markdown("---")

with st.sidebar:
    st_lottie(lottie_truck, height=120)
    
    # Custom Navigation replacing the "annoying" radio buttons
    page = option_menu(
        menu_title="Logistics Command",
        options=["Dashboard", "New Shipment", "History & Tracking", "Agent Insights"],
        icons=["grid-1x2", "plus-circle", "clock-history", "cpu"], # Professional icons
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "5!important", "background-color": "#16181D"},
            "icon": {"color": "#625DF5", "font-size": "18px"}, 
            "nav-link": {"font-size": "14px", "text-align": "left", "margin":"5px", "--hover-color": "#2B2E36"},
            "nav-link-selected": {"background-color": "#625DF5"},
        }
    )
# ---------------------------------------------------------
# PAGE 1: DASHBOARD (The Big Picture)
# ---------------------------------------------------------
# ---------------------------------------------------------
# PAGE 1: DASHBOARD (The Big Picture)
# ---------------------------------------------------------
if page == "Dashboard":
    st.title("Logistics Command Center")
    total_count = 0
    
    # 1. Safety Check for DB
    if db is not None:
        try:
            total_count = db.history.count_documents({})
        except Exception:
            total_count = "Error"
    else:
        total_count = "Offline"

    # 2. Display Metrics
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Total Shipments", total_count)
    with col_b:
        st.metric("Active Agents", "3")
    with col_c:
        st.metric("System Status", "Ready" if db is not None else "Offline", 
          delta="Healthy" if db is not None else "SSL Issue", 
          delta_color="normal" if db is not None else "inverse")

    st.markdown("---")
    st.subheader("Recent Activity")

    # 3. Safety Check for Table
    if db is not None:
        try:
            recent_data = list(db.history.find().sort("timestamp", -1).limit(5))
            if recent_data:
                df = pd.DataFrame([
                    {
                        "Time": r['timestamp'].strftime("%H:%M:%S"), 
                        "Route": f"{r['details']['source']} ➔ {r['details']['destination']}",
                        "Status": r['status']
                    } for r in recent_data
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No recent shipments found.")
        except Exception as e:
            st.error(f"Could not load activity: {e}")
    else:
        st.warning("Database is offline. Please check your MongoDB SSL settings and Network Access.")
# ---------------------------------------------------------
# PAGE 2: NEW SHIPMENT (The Action)
# ---------------------------------------------------------
elif page == "New Shipment":
    st.title("AI-Powered Shipment Booking")
    st.write("Enter details to trigger the Multi-Agent orchestration.")

    with st.container(border=True):
        col_a, col_b = st.columns(2)
        with col_a:
            source = st.text_input("Source City", placeholder="e.g. Bangalore")
            dest = st.text_input("Destination City", placeholder="e.g. Chennai")
        with col_b:
            weight = st.number_input("Weight (kg)", min_value=0.1, step=0.1)
            priority = st.selectbox("Priority Level", ["Low", "Medium", "High"])

        process_btn = st.button("🔥 Process Shipment", use_container_width=True)

    if process_btn:
        if not source or not dest:
            st.warning("Please enter both Source and Destination.")
        else:
            with st.status("🤖 Agents are collaborating...", expanded=True) as status:
                try:
                    # Execute the Crew
                    inputs = {
                        'weight': str(weight), 
                        'destination': dest, 
                        'source': source, 
                        'priority': priority
                    }
                    result = EshipzOrchestrator().crew().kickoff(inputs=inputs)
                    
                    # --- SAVE TO MONGODB ---
                    if db is not None:
                        shipment_record = {
                            "timestamp": datetime.datetime.now(),
                            "details": inputs,
                            "agent_output": str(result),
                            "status": "Booked"
                        }
                        db.history.insert_one(shipment_record)
                        st.toast("✅ Saved to MongoDB Atlas")

                    status.update(label="✅ Shipment Processed Successfully!", state="complete")
                    st.success("Orchestration Complete")
                    st.markdown(f"### Final Agent Report\n{result.raw}")
                    
                except Exception as e:
                    status.update(label="❌ Error occurred", state="error")
                    st.error(f"Execution failed: {e}")

# ---------------------------------------------------------
# PAGE 3: HISTORY & TRACKING (The Memory)
# ---------------------------------------------------------
elif page =="History & Tracking":
    st.title("Shipment Ledger")
    st.write("Historical records retrieved from MongoDB.")

    if db is not None:
        search = st.text_input("Search by Destination")
        query = {}
        if search:
            query = {"details.destination": {"$regex": search, "$options": "i"}}
            
        history = list(db.history.find(query).sort("timestamp", -1))
        
        if history:
            for item in history:
                with st.expander(f"📦 ID: {item['_id']} | {item['timestamp'].strftime('%Y-%m-%d %H:%M')}"):
                    st.write(f"**Route:** {item['details']['source']} to {item['details']['destination']}")
                    st.write(f"**Weight:** {item['details']['weight']} kg")
                    st.info(f"**Agent Decision:**\n{item['agent_output']}")
        else:
            st.info("No records found in the database.")

# ---------------------------------------------------------
# PAGE 4: AGENT INSIGHTS (The Transparency)
# ---------------------------------------------------------
elif page == "Agent Insights":
    st.title("Agent Intelligence Profiles")
    st.write("Understand the roles of your autonomous workers.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("🕵️ Planner")
        st.write("Selects carriers based on cost, weight, and distance.")
    with col2:
        st.subheader("📝 Booker")
        st.write("Generates AWBs and triggers Barcode tools.")
    with col3:
        st.subheader("📡 Tracker")
        st.write("Predicts shipment status and network health.")

    st.markdown("---")
    st.subheader("System Architecture")
    st.code("""
    Frontend: Streamlit (UI)
    Orchestration: CrewAI (Agent Framework)
    Intelligence: Gemini 2.5 Flash-Lite (LLM)
    Database: MongoDB Atlas (NoSQL)
    Tools: Python Barcode & Network Ping
    """)