import streamlit as st
from shipment.crew import EshipzOrchestrator

st.title("Eshipz: Autonomous Logistics Orchestrator")

weight = st.number_input("Package Weight (kg)", value=1.0)
dest = st.text_input("Destination City", value="Mumbai")
priority = st.selectbox("Priority", ["High", "Medium", "Low"])

if st.button("Process Shipment"):
    with st.spinner("Agents are working..."):
        inputs = {'weight': str(weight), 'destination': dest, 'priority': priority}
        result = EshipzOrchestrator().crew().kickoff(inputs=inputs)
        st.success("Shipment Orchestrated!")
        st.markdown(result)
        st.image("shipping_label.png", caption="Generated Shipping Label")