import streamlit as st
import json

def apply_custom_css(path="assets/style.css"):
    """Injects professional CSS into the Streamlit app."""
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def load_lottie_file(path):
    """Loads a JSON animation file."""
    with open(path, "r") as f:
        return json.load(f)
    
def apply_custom_css():
    with open("assets/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)