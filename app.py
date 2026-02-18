import streamlit as st
import os
from dotenv import load_dotenv
from shipment.crew import EshipzOrchestrator
from PIL import Image

# Load environment variables from .env
load_dotenv()

st.set_page_config(page_title="Eshipz AI", layout="wide", page_icon="📦")

# --- Sidebar Configuration ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2311/2311145.png", width=100)
    st.title("Eshipz Settings")
    # Updated info to reflect the working model
    st.info("This AI orchestrator uses Gemini 2.5 Flash for reliable logistics.")
    
    if st.button("Clear Cache/Old Labels"):
        if os.path.exists("shipping_label.png"):
            os.remove("shipping_label.png")
            st.success("Cache cleared!")
            st.rerun()

# --- Main UI ---
st.title("📦 Eshipz: Autonomous Logistics Orchestrator")
st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Shipment Details")
    weight = st.number_input("Package Weight (kg)", min_value=0.1, value=1.0, step=0.1)
    dest = st.text_input("Destination City", value="Chennai")
    priority = st.selectbox("Priority", ["High", "Medium", "Low"])
    
    process_btn = st.button("🚀 Process Shipment", use_container_width=True)

with col2:
    if process_btn:
        # Status container provides real-time feedback on agent activity
        with st.status("🤖 AI Agents at work...", expanded=True) as status:
            try:
                # Prepare the inputs for the crew
                inputs = {
                    'weight': str(weight), 
                    'destination': dest, 
                    'priority': priority
                }
                
                st.write("🔍 Strategy Agent: Analyzing carrier options...")
                # Kickoff the sequential process
                result = EshipzOrchestrator().crew().kickoff(inputs=inputs)
                
                status.update(label="✅ Shipment Orchestrated!", state="complete", expanded=False)
                
                st.subheader("Process Summary")
                # Using .raw to display the final tracking report
                st.info(result.raw) 

                # Layout for result and barcode
                res_col, img_col = st.columns(2)
                
                with res_col:
                    st.success("Logistics Plan Generated")
                
                with img_col:
                    if os.path.exists("shipping_label.png"):
                        st.image("shipping_label.png", caption="Generated Barcode")
                        with open("shipping_label.png", "rb") as file:
                            st.download_button(
                                label="💾 Download Label",
                                data=file,
                                file_name=f"label_{dest}.png",
                                mime="image/png",
                                use_container_width=True
                            )
            except Exception as e:
                status.update(label="❌ Execution Failed", state="error")
                st.error(f"Error: {e}")
    else:
        st.info("Enter shipment details and click 'Process Shipment' to start the AI workflow.")