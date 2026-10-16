import os
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client, Client

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

# 2. API Key & Supabase Setup
st.sidebar.markdown("### Debug Menu")
ui_key = st.sidebar.text_input("Paste Groq API Key here to force connection:", type="password")

GROQ_API_KEY = ui_key or st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))

if not GROQ_API_KEY:
    st.error("🚨 API Key missing! Please open the sidebar (top left > icon) and paste your key.")
    st.stop()

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("🚨 Supabase credentials missing! Please configure SUPABASE_URL and SUPABASE_KEY in your secrets.")
    st.stop()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. Supabase Inventory & Daily Tracking Engine
def get_pantry_inventory():
    """Fetches the live inventory items from Supabase."""
    try:
        response = supabase.table("inventory").select("*").execute()
        return response.data
    except Exception as e:
        return []

def get_total_distributed():
    """Tracks daily claims using a lightweight metadata table or local state fallback."""
    # We can query total remaining or handle distribution counts dynamically
    inventory = get_pantry_inventory()
    total_stock = sum([item.get('quantity', 0) for item in inventory])
    return total_stock

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

# 5. Dynamic Non-Profit System Prompt with Supabase Inventory Context
def build_system_prompt():
    inventory_data = get_pantry_inventory()
    return f"""You are Monique, the empathetic, efficient Floor Manager for Cultivating Community, a community food pantry in Washington, D.C.

LIVE PANTRY INVENTORY DATABASE:
{inventory_data}

NON-PROFIT OPERATIONAL RULES:
1. EVERYTHING IS 100% FREE: Never discuss buying, selling, prices, or payments. If someone asks to buy an item or ask about cost, warmly clarify that all food is completely free of charge.
2. ACCURATE STOCK & DIALECT FLEXIBILITY: Accurately answer what items we have in stock using ONLY the live inventory database above. If someone asks using slang, Ebonics, different dialects, or another language (like Spanish), understand their intent semantically and match it to our inventory items (such as Call Your Mother bakery items, fresh produce, canned goods, staples, or our two hot prepared options: Curry and Corned Beef Sandwiches).
3. ABSOLUTE PRIVACY: NEVER ask for names, IDs, phone numbers, addresses, immigration status, or reasons for needing assistance.
4. DYNAMIC LANGUAGE MATCHING: Detect the visitor's language automatically and respond in the EXACT SAME language.
5. CONCISE & ACTION-ORIENTED: Keep all responses to 1-2 warm sentences. Always direct visitors to tap the green 'Claim Ration' button on the screen to receive their package today."""

# 6. Smooth State Management Initialization
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": build_system_prompt()}]
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0
if "claim_success" not in st.session_state:
    st.session_state.claim_success = False
if "session_active" not in st.session_state:
    st.session_state.session_active = False
if "speak_greeting" not in st.session_state:
    st.session_state.speak_greeting = False

# 7. Button Callback Logic
def start_session():
    st.session_state.session_active = True
    greeting = "Hi, I'm Monique. How can I help you today?"
    # Update system prompt with fresh inventory on session start
    st.session_state.messages[0] = {"role": "system", "content": build_system_prompt()}
    st.session_state.messages.append({"role": "assistant", "content": greeting})
    st.session_state.speak_greeting = greeting  

def process_claim():
    # Reset conversation and trigger success state for the next visitor
    st.session_state.messages = [{"role": "system", "content": build_system_prompt()}]
    st.session_state.audio_key += 1
    st.session_state.claim_success = True
    st.session_state.session_active = False  

# 8. Main UI  
st.title("Community Pantry Kiosk")

inventory_items = get_pantry_inventory()
total_quantity = sum([item.get('quantity', 0) for item in inventory_items])
st.metric(label="Total Items Available Today", value=total_quantity)

if st.session_state.claim_success:
    st.success("✅ Ration claimed! Ready for the next person.")
    st.session_state.claim_success = False

# 9. Session Routing: Start Screen vs Active Chat
if not st.session_state.session_active:
    st.write("---")
    st.button("👋 Press to Begin", on_click=start_session, use_container_width=True, type="primary")

else:
    if st.session_state.speak_greeting:
        speak_text(st.session_state.speak_greeting)
        st.session_state.speak_greeting = False

    # Display chat history
    for msg in st.session_state.messages:
        if msg["role"] != "system":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Voice Input
    audio_value = st.audio_input("Tap the microphone to reply", key=f"mic_{st.session_state.audio_key}")

    if audio_value:
        with st.spinner("Listening..."):
            try:
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

                    # Generate AI Response with live Supabase inventory context
                    with st.chat_message("assistant"):
                        with st.spinner("Processing..."):
                            completion = client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=st.session_state.messages,
                                temperature=0.2,
                                max_tokens=120
                            )
                            response_text = completion.choices[0].message.content
                            st.markdown(response_text)
                            st.session_state.messages.append({"role": "assistant", "content": response_text})
                            
                            speak_text(response_text)

            except Exception as e:
                st.error(f"Connection issue: {e}. Please verify your network connection or API key.")

    st.divider()

    # Single-Click Claim Button
    st.button("✅ Claim Ration", use_container_width=True, type="primary", on_click=process_claim, disabled=(total_quantity <= 0))

    if total_quantity <= 0:
        st.error("Daily rations are currently empty for today.")
