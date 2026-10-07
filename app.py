import os
import sqlite3
from datetime import date
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

# 2. Initialize Client using OpenAI SDK pointed at Groq's Endpoint
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))

# Graceful fallback if the key is missing from Streamlit Cloud Secrets
if not GROQ_API_KEY:
    st.error("🚨 API Key missing! Please add GROQ_API_KEY to your Streamlit Cloud Secrets dashboard.")
    st.stop()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# 3. Anonymous Daily Ration Engine (SQLite)
def init_db():
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (date TEXT PRIMARY KEY, total_kits INTEGER, distributed INTEGER)''')
    
    today = date.today().isoformat()
    c.execute("SELECT * FROM inventory WHERE date=?", (today,))
    if not c.fetchone():
        c.execute("INSERT INTO inventory VALUES (?, ?, ?)", (today, 150, 0)) # Default 150 daily kits
    conn.commit()
    conn.close()

def get_inventory():
    today = date.today().isoformat()
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute("SELECT total_kits, distributed FROM inventory WHERE date=?", (today,))
    result = c.fetchone()
    conn.close()
    return result if result else (150, 0)

def claim_ration():
    today = date.today().isoformat()
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute("UPDATE inventory SET distributed = distributed + 1 WHERE date=?", (today,))
    conn.commit()
    conn.close()

init_db()

# 4. Zero-Cost Browser Text-to-
