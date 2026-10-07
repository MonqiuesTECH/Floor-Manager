import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
import sqlite3
from datetime import date
import os

# 1. Setup & Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

# Initialize Groq client (requires GROQ_API_KEY in .streamlit/secrets.toml)
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
client = Groq(api_key=GROQ_API_KEY)

# 2. Anonymous Daily Ration Engine
def init_db():
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (date TEXT PRIMARY KEY, total_kits INTEGER, distributed INTEGER)''')
    
    today = date.today().isoformat()
    c.execute("SELECT * FROM inventory WHERE date=?", (today,))
    if not c.fetchone():
        c.execute("INSERT INTO inventory VALUES (?, ?, ?)", (today, 150, 0)) # Defaults to 150 daily kits
    conn.commit()
    conn.close()

def get_inventory():
    today = date.today().isoformat()
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute("SELECT total_kits, distributed FROM inventory WHERE date=?", (today,))
    result = c.fetchone()
    conn.close()
    return result

def claim_ration():
    today = date.today().isoformat()
    conn = sqlite3.connect("pantry_state.db")
    c = conn.cursor()
    c.execute("UPDATE inventory SET distributed = distributed + 1 WHERE date=?", (today,))
    conn.commit()
    conn.close()

init_db()

# 3. Web Speech API (Text-to-Speech)
def speak_text(text):
    """Injects native browser Web Speech API for zero-cost audio playback."""
    clean_text = text.replace('"', "'").replace('\n', ' ')
    js_code = f"""
    <script>
        const utterance = new SpeechSynthesisUtterance("{clean_text}");
        window.speechSynthesis.speak(utterance);
    </script>
    """
    components.html(js_code, height=0, width=0)

# 4. Core System Prompt
SYSTEM_PROMPT = """You are the Floor Manager for a community food pantry. 
Your job is to welcome visitors, confirm they want a food ration today, and guide them.
CRITICAL RULES:
1. NEVER ask for a name, ID, or reason for needing food.
2. Automatically detect the user's language and reply in the EXACT SAME language.
3. Keep responses strictly to 1-2 short sentences.
4. If they confirm they want food, politely tell them to tap the green "Claim Ration" button on the screen."""

# 5. Kiosk UI & Logic
st.title("Community Pantry Kiosk")

total, distributed = get_inventory()
st.metric(label="Rations Remaining Today", value=total - distributed)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Display chat history (omitting the hidden system prompt)
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# Voice Input via Streamlit Audio Widget
audio_value = st.audio_input("Tap to speak to the Floor Manager")

if audio_value:
    # 1. Transcribe Audio (using Groq Whisper API for speed)
    with st.spinner("Listening..."):
        transcription = client.audio.transcriptions.create(
            file=("audio.wav", audio_value.read()),
            model="whisper-large-v3-turbo",
            response_format="text"
        )
    
    st.session_state.messages.append({"role": "user", "content": transcription})
    with st.chat_message("user"):
        st.markdown(transcription)

    # 2. Generate LLM Response (Translation & Logic)
    with st.chat_message("assistant"):
        with st.spinner("Translating..."):
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=st.session_state.messages,
                temperature=0.3,
                max_tokens=100
            )
            response_text = completion.choices[0].message.content
            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            
            # Trigger Browser TTS
            speak_text(response_text)

st.divider()

# 6. Anonymous Check-in Button
if st.button("✅ Claim Ration", use_container_width=True, type="primary"):
    if total - distributed > 0:
        claim_ration()
        st.success("Ration claimed! The counter has been updated anonymously.")
        # Clear chat session for the next person in line
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    else:
        st.error("Daily rations are currently empty.")
