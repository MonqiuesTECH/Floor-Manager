import os
import re
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="wide")

# 2. Secure Secret Configuration
SUPABASE_URL = "https://qvmabwhlqzngzncawlue.supabase.co"
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))

if not GROQ_API_KEY or not SUPABASE_KEY:
    st.error("🚨 Please ensure SUPABASE_KEY and GROQ_API_KEY are configured in your Streamlit secrets (.streamlit/secrets.toml).")
    st.stop()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. Supabase Inventory & Basket Logging
def get_pantry_inventory():
    try:
        response = supabase.table("inventory").select("*").execute()
        return response.data
    except Exception as e:
        return []

def save_basket_to_supabase(basket_data, pickup_ticket):
    """Saves the basket anonymously and returns the unique record ID for the QR code."""
    try:
        response = supabase.table("baskets").insert({
            "items": basket_data,
            "pickup_time": pickup_ticket["time"],
            "pickup_location": pickup_ticket["location"]
        }).execute()
        if response.data:
            return response.data[0].get('id')
    except Exception as e:
        print(f"Error saving basket to Supabase: {e}")
    return None

# 4. Zero-Cost Browser Text-to-Speech JS Injection
def speak_text(text):
    clean_text = re.sub(r'[*_#]', '', text)
    clean_text = clean_text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    
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

# 5. Dynamic System Prompt
def build_system_prompt(dynamic_alert=""):
    inventory_data = get_pantry_inventory()
    basket = st.session_state.get("basket", {})
    
    category_counts = {}
    for item_name, details in basket.items():
        cat = details['category']
        category_counts[cat] = category_counts.get(cat, 0) + details['quantity']
        
    available_categories = {item['category'] for item in inventory_data} if inventory_data else {"Produce", "Bakery", "Dry Goods"}
    allowances = []
    for cat in available_categories:
        used = category_counts.get(cat, 0)
        remaining = max(0, 3 - used)
        allowances.append(f"- {cat}: {remaining} items remaining")
        
    allowance_text = "\n".join(allowances)
    basket_summary = str(basket) if basket else "Empty"

    alert_section = f"\n\nCRITICAL REAL-TIME ALERT: {dynamic_alert}\n\n" if dynamic_alert else ""

    prompt = (
        "You are Monique, the gracious, eloquent, and deeply caring Floor Manager for Cultivating Community, a community food pantry in Washington, D.C. "
        "Your voice and tone embody the poise, warmth, and inspiring elegance of Michelle Obama—welcoming, dignified, articulate, and deeply supportive of our community.\n\n"
        "CRITICAL RULE: You MUST always respond with at least one complete sentence. Never remain silent.\n\n"
        "LIVE PANTRY INVENTORY DATABASE:\n"
        f"{inventory_data}\n\n"
        "CURRENT VISITOR BASKET:\n"
        f"{basket_summary}\n\n"
        "REMAINING DEPARTMENT ALLOWANCES (Max 3 per department):\n"
        f"{allowance_text}"
        f"{alert_section}"
        "NON-PROFIT OPERATIONAL RULES:\n"
        "1. OUT OF STOCK ITEMS: If the visitor asks for an item that is NOT in the LIVE PANTRY INVENTORY DATABASE, politely inform them that we do not have it today, and immediately suggest 2 specific alternatives from the database that we DO have.\n"
        "2. EVERYTHING IS 100% FREE: Never discuss buying, selling, prices, or payments.\n"
        "3. LIMITS: If asked what they can add, check 'REMAINING DEPARTMENT ALLOWANCES'. If a category is full, let them know gently and suggest another department.\n"
        "4. ABSOLUTE PRIVACY: NEVER ask for names, IDs, phone numbers, or addresses. Emphasize that their pickup is 100% anonymous via a QR code.\n"
        "5. CONCISE & WARM: Keep responses to 2-3 polished sentences. Direct visitors to check their basket on the sidebar and tap 'Claim Ration' when finished."
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
    greeting = "Welcome to Cultivating Community. You are welcome to select up to 3 items from each of our food departments today—how may I assist you with your basket?"
    st.session_state.messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "assistant", "content": greeting}
    ]
    st.session_state.speak_greeting = greeting  

def process_claim():
    pickup_time = (datetime.now() + timedelta(minutes=30)).strftime("%I:%M %p")
    ticket = {
        "time": pickup_time,
        "location": "Cultivating Community Pickup Hub (Dandelion Collective)"
    }
    
    # Save to Supabase and get the anonymous record ID
    basket_snapshot = st.session_state.basket.copy()
    ticket_id = save_basket_to_supabase(basket_snapshot, ticket)
    
    ticket["id"] = ticket_id if ticket_id else "ANON-PASS"
    st.session_state.pickup_ticket = ticket
    st.session_state.claim_success = True
    st.session_state.basket = {}

# NLP Parsing & Adding Logic
def extract_quantity(text_lower, item_keywords):
    num_map = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3}
    words = text_lower.split()
    for i, word in enumerate(words):
        for kw in item_keywords:
            if kw in word:
                if i > 0 and words[i-1] in num_map:
                    return num_map[words[i-1]]
    for num_str, val in num_map.items():
        if re.search(r'\b' + num_str + r'\b', text_lower):
            return val
    return 1 

def check_and_auto_add_cart(user_text, inventory_items):
    text_lower = user_text.lower()
    added = []
    rejected = []
    
    for item in inventory_items:
        iname = item['item_name']
        iname_lower = iname.lower()
        
        stop_words = {'fresh', 'canned', 'bags', 'bundles', 'artisan', 'call', 'your', 'mother', 'and', 'the', 'with', 'some'}
        key_words = [w for w in iname_lower.split() if w not in stop_words and len(w) > 2]
        
        matched = False
        if iname_lower in text_lower:
            matched = True
        else:
            for kw in key_words:
                base_word = kw.rstrip('s')
                pattern = r'\b' + re.escape(base_word) + r'(?:s|es)?\b'
                if re.search(pattern, text_lower):
                    matched = True
                    break
                    
        if matched:
            cat = item['category']
            req_qty = extract_quantity(text_lower, key_words)
            
            current_qty = st.session_state.basket.get(iname, {}).get("quantity", 0)
            cat_count = sum(d['quantity'] for d in st.session_state.basket.values() if d['category'] == cat)
            
            available_space = 3 - cat_count
            add_amount = min(req_qty, available_space, 3 - current_qty)
            
            if add_amount > 0:
                st.session_state.basket[iname] = {"category": cat, "quantity": current_qty + add_amount}
                added.append(iname)
                if req_qty > add_amount:
                    rejected.append({"name": iname, "category": cat})
            else:
                rejected.append({"name": iname, "category": cat})
                
    return added, rejected

# 8. Main UI Layout (Visual Grid + Sidebar POS Style)
st.title("🍲 Cultivating Community — Floor Manager Kiosk")

inventory_items = get_pantry_inventory()
total_quantity = sum([item.get('quantity', 0) for item in inventory_items])

# Sidebar: Basket, QR Ticket & Summary
with st.sidebar:
    st.markdown("### 🛒 Your Custom Basket")
    if st.session_state.basket:
        for item_name, details in st.session_state.basket.items():
            st.text(f"• {item_name} (Qty: {details['quantity']})")
        if st.button("Clear Basket", use_container_width=True):
            st.session_state.basket = {}
            st.rerun()
    else:
        st.info("Your basket is empty. Select items below or talk to Monique!")

    st.markdown("---")
    st.metric(label="Total Pantry Stock Available", value=total_quantity)
    
    if st.session_state.claim_success and st.session_state.pickup_ticket:
        ticket = st.session_state.pickup_ticket
        st.success(f"✅ Ration Claimed Successfully!")
        st.markdown(f"🕒 **Pickup Time:** {ticket['time']}")
        st.markdown(f"📍 **Location:** {ticket['location']}")
        
        # Generate Anonymous QR Code pointing to the Supabase record ID
        qr_data = f"Cultivating-Community-Ticket-{ticket['id']}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={qr_data}"
        st.image(qr_url, caption=f"Scan to Verify (ID: {ticket['id']})", width=180)
        st.caption("🔒 100% Anonymous: No personal information was collected.")

        if st.button("Start New Visit", use_container_width=True):
            st.session_state.claim_success = False
            st.session_state.pickup_ticket = None
            st.session_state.session_active = False
            st.session_state.messages = []
            st.rerun()
    else:
        st.button("✅ Claim Ration & Get QR Code", use_container_width=True, type="primary", on_click=process_claim, disabled=(total_quantity <= 0 or not st.session_state.basket))

# Main Body Split: Left = Visual Grid of Inventory Cards, Right = Monique Chat
col_grid, col_chat = st.columns([1.2, 1])

with col_grid:
    st.markdown("### 📦 Available Pantry Inventory")
    if not inventory_items:
        st.warning("No inventory loaded in Supabase yet.")
    else:
        cols = st.columns(3)
        for index, item in enumerate(inventory_items):
            with cols[index % 3]:
                with st.container(border=True):
                    st.markdown(f"**{item['item_name']}**")
                    st.caption(f"Category: {item['category']}")
                    st.markdown(f"Stock: **{item['quantity']} {item['unit']}**")
                    
                    if st.button("Add 1", key=f"grid_add_{item['id']}", use_container_width=True):
                        if not st.session_state.session_active:
                            start_session()
                        cat = item['category']
                        iname = item['item_name']
                        current_q = st.session_state.basket.get(iname, {}).get("quantity", 0)
                        cat_count = sum(d['quantity'] for d in st.session_state.basket.values() if d['category'] == cat)
                        
                        if cat_count < 3 and current_q < 3:
                            st.session_state.basket[iname] = {"category": cat, "quantity": current_q + 1}
                            st.success(f"Added {iname}!")
                            st.rerun()
                        else:
                            st.error("Limit reached (Max 3 per department)!")

with col_chat:
    st.markdown("### 💬 Monique (Virtual Floor Manager)")
    
    if not st.session_state.session_active:
        st.info("Tap the button below to start your conversation with Monique.")
        st.button("👋 Press to Begin Session", on_click=start_session, use_container_width=True, type="primary")
    else:
        if st.session_state.speak_greeting:
            speak_text(st.session_state.speak_greeting)
            st.session_state.speak_greeting = False

        chat_container = st.container(height=400)
        with chat_container:
            for msg in st.session_state.messages:
                if msg["role"] != "system":
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

        user_input_text = ""
        audio_value = st.audio_input("🎤 Tap to talk", key=f"mic_{st.session_state.audio_key}")
        chat_text = st.chat_input("✨ Or type your request...")

        if audio_value:
            with st.spinner("Listening..."):
                try:
                    transcription = client.audio.transcriptions.create(
                        file=("audio.wav", audio_value.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text"
                    )
                    user_input_text = transcription.strip() if isinstance(transcription, str) else getattr(transcription, "text", "").strip()
                except Exception as e:
                    st.error(f"Transcription error: {e}")
        elif chat_text:
            user_input_text = chat_text

        if user_input_text:
            if len(st.session_state.messages) > 11:
                st.session_state.messages = [st.session_state.messages[0]] + st.session_state.messages[-10:]

            st.session_state.messages.append({"role": "user", "content": user_input_text})
            added_items, rejected_items = check_and_auto_add_cart(user_input_text, inventory_items)
            
            dynamic_context = ""
            if rejected_items:
                rej_names = [r["name"] for r in rejected_items]
                rej_cat = rejected_items[0]["category"]
                dynamic_context = (
                    f"The visitor just tried to add {', '.join(rej_names)}, but they already hit their 3-item limit for the '{rej_cat}' department. "
                    f"You MUST explicitly tell them they cannot add any more {rej_cat} items right now, and suggest something else."
                )
                
            with st.spinner("Monique is responding..."):
                if st.session_state.messages and st.session_state.messages[0]["role"] == "system":
                    st.session_state.messages[0]["content"] = build_system_prompt(dynamic_context)
                else:
                    st.session_state.messages.insert(0, {"role": "system", "content": build_system_prompt(dynamic_context)})
                
                try:
                    completion = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=st.session_state.messages,
                        temperature=0.4,
                        max_tokens=250
                    )
                    response_text = completion.choices[0].message.content
                    
                    if not response_text or not response_text.strip():
                        response_text = "I'm sorry, I didn't quite catch that. Could you please repeat what you'd like to add to your basket?"
                        
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    st.session_state.speak_greeting = response_text
                    
                except Exception as e:
                    st.error(f"Connection issue: {e}")
                        
            st.session_state.audio_key += 1
            st.rerun()
