import os
import sqlite3
from datetime import date
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

# 2. API Key Setup
st.sidebar.markdown("### Debug Menu")
ui_key = st.sidebar.text_input("Paste Groq API Key here to force connection:", type="password")

GROQ_API_KEY = ui_key or st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))

if not GROQ_API_KEY:
    st.error("🚨 API Key missing! Please open the sidebar (top left > icon) and paste your key.")
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

# 5. Non-Profit Logic & System Guardrails
SYSTEM_PROMPT = """You are the empathetic, efficient Floor Manager for a community food pantry.

NON-PROFIT OPERATIONAL RULES:
1. EVERYTHING IS 100% FREE: Never discuss buying, selling, prices, or payments. If someone asks to buy an item or ask about cost, warmly clarify that all food is completely free of charge.
2. PRE-PACKED RATION KITS: We distribute standard, pre-assembled food ration kits (containing fresh produce, canned goods, and staples). We do not fulfill custom grocery orders or individual item sales.
3. ABSOLUTE PRIVACY: NEVER ask for names, IDs, phone numbers, addresses, immigration status, or reasons for needing assistance.
4. DYNAMIC LANGUAGE MATCHING: Detect the visitor's language automatically and respond in the EXACT SAME language.
5. CONCISE & ACTION-ORIENTED: Keep all responses to 1-2 warm sentences. Always direct visitors to tap the green 'Claim Ration' button on the screen to receive their package today."""

# 6. Smooth State Management Initialization
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0
if "claim_success" not in st.session_state:
    st.session_state.claim_success = False

# 7. Button Callback Logic
def process_claim():
    t, d = get_inventory()
    if t - d > 0:
        claim_ration()
        # Wipe the chat history clean
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Increment the audio key to force the microphone widget to reset
        st.session_state.audio_key += 1
        # Set a flag to show a success banner on the next render
        st.session_state.claim_success = True

# 8. User Interface Rendering
st.title("Community Pantry Kiosk")

total, distributed = get_inventory()
remaining = total - distributed
st.metric(label="Rations Remaining Today", value=remaining)

# Display the success banner if the button was just clicked
if st.session_state.claim_success:
    st.success("✅ Ration claimed! Ready for the next person.")
    st.session_state.claim_success = False

# Display chat history
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 9. Voice Input & Processing (Using dynamic key)
audio_value = st.audio_input("Tap the microphone to speak to the Floor Manager", key=f"mic_{st.session_state.audio_key}")

if audio_value:
    with st.spinner("Listening..."):
        try:
            # Transcribe voice input
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

                # Generate AI Response
                with st.chat_message("assistant"):
                    with st.spinner("Processing..."):
                        completion = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=st.session_state.messages,
                            temperature=0.2,
                            max_tokens=120
                        )
                        response_text = completion.choices[0].message.content
                        st.markdown(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                        
                        # Trigger Speech Synthesis
                        speak_text(response_text)

        except Exception as e:
            st.error(f"Connection issue: {e}. Please verify your network connection or API key.")

st.divider()

# 10. Single-Click Claim Button
st.button("✅ Claim Ration", use_container_width=True, type="primary", on_click=process_claim, disabled=(remaining <= 0))

if remaining <= 0:
    st.error("Daily rations are currently empty for today.")
