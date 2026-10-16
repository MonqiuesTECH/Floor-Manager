import os
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

# 2. Secure Secret Configuration (No UI Inputs)
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))

if not GROQ_API_KEY or not SUPABASE_URL or not SUPABASE_KEY:
    st.error("🚨 Required API keys or Supabase credentials are missing from your Streamlit secrets configuration.")
    st.stop()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. Supabase Inventory Engine
def get_pantry_inventory():
    """Fetches the live inventory items from Supabase."""
    try:
        response = supabase.table("inventory").select("*").execute()
        return response.data
    except Exception as e:
        return []

# 4. Zero-Cost Browser Text-to-Speech JS Injection
def speak_text(text):
    clean_text = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    js_code = (
        "<script>\n"
        "if ('speechSynthesis' in window) {\n"
        "    window.speechSynthesis.cancel();\n"
        f"    const utterance = new SpeechSynthesisUtterance(\"{clean_text}\");\n"
        "    window.speechSynthesis.speak(utterance);\n"
        "}\n"
        "</script>"
    )
    components.html(js_code, height=0, width=0)

# 5. Dynamic Non-Profit System Prompt with Persona & Live Basket
def build_system_prompt():
    inventory_data = get_pantry_inventory()
    basket_data = st.session_state.get("basket", {})
    prompt = (
        "You are Monique, the warm, nurturing, and efficient Floor Manager for Cultivating Community, a community food pantry in Washington, D.C. "
        "Your voice and tone are that of a grounded, caring Black woman—welcoming, respectful, community-oriented, and real (using warm expressions like 'Hey honey', 'Got you covered', or 'Fam' naturally when appropriate).\n\n"
        "LIVE PANTRY INVENTORY DATABASE:\n"
        f"{inventory_data}\n\n"
        "CURRENT VISITOR BASKET (What they have selected so far):\n"
        f"{basket_data}\n\n"
        "NON-PROFIT OPERATIONAL RULES:\n"
        "1. EVERYTHING IS 100% FREE: Never discuss buying, selling, prices, or payments. All food is completely free of charge.\n"
        "2. BASKET & LIMITS: Visitors can choose up to 3 items from each food department. Acknowledge what they have added to their basket warmly and let them know what else they can pick.\n"
        "3. ACCURATE STOCK & DIALECT FLEXIBILITY: Accurately answer what items we have in stock using ONLY the live inventory database. Understand slang, Ebonics, different dialects, or other languages semantically.\n"
        "4. ABSOLUTE PRIVACY: NEVER ask for names, IDs, phone numbers, addresses, immigration status, or reasons for needing assistance.\n"
        "5. DYNAMIC LANGUAGE MATCHING: Detect the visitor's language automatically and respond in the EXACT SAME language.\n"
        "6. CONCISE & ACTION-ORIENTED: Keep all responses to 1-2 warm sentences. Direct visitors to check their basket on the sidebar and tap the green 'Claim Ration' button when they're finished."
    )
    return prompt

# 6. Smooth State Management Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0
if "claim_success" not in st.session_state:
    st.session_state.claim_success = False
if "session_active" not in st.session_state:
    st.session_state.session_active = False
if "speak_greeting" not in st.session_state:
    st.session_state.speak_greeting = False
if "basket" not in st.session_state:
    st.session_state.basket = {}  
if "pickup_ticket" not in st.session_state:
    st.session_state.pickup_ticket = None

# 7. Button Callback Logic
def start_session():
    st.session_state.session_active = True
    greeting = "Hey honey! Welcome to Cultivating Community. You can pick up to 3 items from each food department today—what can I add to your basket?"
    st.session_state.messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "assistant", "content": greeting}
    ]
    st.session_state.speak_greeting = greeting  

def process_claim():
    pickup_time = (datetime.now() + timedelta(minutes=30)).strftime("%I:%M %p")
    st.session_state.pickup_ticket = {
        "time": pickup_time,
        "location": "Cultivating Community Pickup Hub (Dandelion Collective)"
    }
    st.session_state.claim_success = True
    st.session_state.basket = {}

# Helper function to auto-add items based on user utterance
def check_and_auto_add_cart(user_text, inventory_items):
    text_lower = user_text.lower()
    for item in inventory_items:
        iname = item['item_name']
        # Check if the item name or significant keywords match the user text
        keywords = [w.lower() for w in iname.split() if len(w) > 2]
        if iname.lower() in text_lower or any(kw in text_lower for kw in keywords):
            cat = item['category']
            current_qty = st.session_state.basket.get(iname, {}).get("quantity", 0)
            cat_count = sum(d['quantity'] for d in st.session_state.basket.values() if d['category'] == cat)
            # Add up to 3 items if under category limit
            if cat_count < 3 and current_qty < 3:
                add_amount = min(3 - current_qty, 3 - cat_count)
                if add_amount > 0:
                    st.session_state.basket[iname] = {"category": cat, "quantity": current_qty + add_amount}

# Function to handle AI response generation smoothly
def generate_monique_response():
    # Always update system prompt with latest basket & inventory state
    if st.session_state.messages and st.session_state.messages[0]["role"] == "system":
        st.session_state.messages[0]["content"] = build_system_prompt()
    else:
        st.session_state.messages.insert(0, {"role": "system", "content": build_system_prompt()})

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=st.session_state.messages,
            temperature=0.3,
            max_tokens=150
        )
        response_text = completion.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": response_text})
        st.session_state.speak_greeting = response_text
    except Exception as e:
        st.error(f"Connection issue: {e}")

# 8. Main UI  
st.title("Community Pantry Kiosk")

inventory_items = get_pantry_inventory()
total_quantity = sum([item.get('quantity', 0) for item in inventory_items])
st.metric(label="Total Items Available Today", value=total_quantity)

# Sidebar Basket Inspector & Manual Selector
st.sidebar.markdown("### 🛒 Your Custom Basket")
if st.session_state.basket:
    for item_name, details in st.session_state.basket.items():
        st.sidebar.text(f"• {item_name} (Qty: {details['quantity']})")
    if st.sidebar.button("Clear Basket"):
        st.session_state.basket = {}
        st.rerun()
else:
    st.sidebar.info("Your basket is empty. Tell Monique what you need!")

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Add to Basket")
selected_item = st.sidebar.selectbox("Select pantry item:", [i['item_name'] for i in inventory_items] if inventory_items else [])
add_qty = st.sidebar.number_input("Quantity", min_value=1, max_value=3, value=1)
if st.sidebar.button("Add Item"):
    matched = next((i for i in inventory_items if i['item_name'] == selected_item), None)
    if matched:
        cat = matched['category']
        cat_count = sum(d['quantity'] for d in st.session_state.basket.values() if d['category'] == cat)
        if cat_count + add_qty <= 3:
            current_q = st.session_state.basket.get(selected_item, {}).get("quantity", 0)
            st.session_state.basket[selected_item] = {"category": cat, "quantity": current_q + add_qty}
            st.success(f"Added {add_qty}x {selected_item} to basket!")
            st.rerun()
        else:
            st.sidebar.error("Limit reached: Max 3 items allowed per food department!")

if st.session_state.claim_success and st.session_state.pickup_ticket:
    ticket = st.session_state.pickup_ticket
    st.success(f"✅ Ration successfully claimed! Please pick up your basket at **{ticket['time']}** today at **{ticket['location']}**.")
    if st.button("Start New Visit"):
        st.session_state.claim_success = False
        st.session_state.pickup_ticket = None
        st.session_state.session_active = False
        st.session_state.messages = []
        st.rerun()

# 9. Session Routing: Start Screen vs Active Chat
if not st.session_state.session_active:
    st.write("---")
    st.button("👋 Press to Begin", on_click=start_session, use_container_width=True, type="primary")

else:
    if st.session_state.speak_greeting:
        speak_text(st.session_state.speak_greeting)
        st.session_state.speak_greeting = False

    # Display chat history cleanly
    for msg in st.session_state.messages:
        if msg["role"] != "system":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    st.markdown("### 💬 Talk or Type to Monique")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        audio_value = st.audio_input("Tap microphone to talk", key=f"mic_{st.session_state.audio_key}")
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        text_submit_btn = st.button("✨ Ask Monique", type="secondary", use_container_width=True)

    user_text = st.chat_input("Type what you need here...")

    # Process Audio Input
    if audio_value:
        with st.spinner("Listening..."):
            try:
                transcription = client.audio.transcriptions.create(
                    file=("audio.wav", audio_value.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text"
                )
                user_text = transcription.strip() if isinstance(transcription, str) else getattr(transcription, "text", "").strip()
            except Exception as e:
                st.error(f"Transcription error: {e}")

    # Handle incoming user message
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        
        # Auto-add requested items to basket
        check_and_auto_add_cart(user_text, inventory_items)
        
        # Generate Monique's response
        generate_monique_response()
        
        st.session_state.audio_key += 1
        st.rerun()

    st.divider()

    # Single-Click Claim Button
    st.button("✅ Claim Ration", use_container_width=True, type="primary", on_click=process_claim, disabled=(total_quantity <= 0 or not st.session_state.basket))

    if not st.session_state.basket:
        st.warning("Add at least one item to your basket before claiming your ration.")

    if total_quantity <= 0:
        st.error("Daily rations are currently empty for today.")
