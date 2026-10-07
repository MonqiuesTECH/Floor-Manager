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

# 4. Zero-Cost Browser Text-to-Speech JS Injection
def speak_text(text):
    clean_text = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    js_code = f"""
    <script>
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance("{clean_text}");
            window.speechSynthesis.speak(utterance);
        }}
    </script>
    """
    components.html(js_code, height=0, width=0)

# 5. System Prompt & Guardrails
SYSTEM_PROMPT = """You are the Floor Manager for a community food pantry. 
Your job is to welcome visitors, answer quick questions, confirm if they want a food ration today, and guide them.

CRITICAL RULES:
1. NEVER ask for a name, ID, phone number, address, or reason for needing aid.
2. Automatically detect the user's language and reply in the EXACT SAME language (even if they switch languages mid-sentence).
3. Keep responses strictly to 1-2 short, warm sentences.
4. If they confirm they want food, politely instruct them to tap the green "Claim Ration" button on the screen."""

# 6. User Interface
st.title("Community Pantry Kiosk")

total, distributed = get_inventory()
remaining = total - distributed
st.metric(label="Rations Remaining Today", value=remaining)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Display chat history
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 7. Voice Input & Processing
audio_value = st.audio_input("Tap the microphone to speak to the Floor Manager")

if audio_value:
    with st.spinner("Listening..."):
        try:
            # Transcribe voice input using Groq's Whisper model via OpenAI client
            transcription = client.audio.transcriptions.create(
                file=("audio.wav", audio_value.read()),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
            
            user_text = transcription.strip() if isinstance(transcription, str) else getattr(transcription, "text", "").strip()

            if user_text:
                st.session_state.messages.append({"role": "user", "content": user_text})
                with st.chat_message("user"):
                    st.markdown(user_text)

                # Generate AI Response using Groq's Llama 3.3 model via OpenAI client
                with st.chat_message("assistant"):
                    with st.spinner
