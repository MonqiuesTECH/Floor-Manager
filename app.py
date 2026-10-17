import os
import re
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Pantry Floor Manager", page_icon="🍲", layout="centered")

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
    try:
        supabase.table("baskets").insert({
            "items": basket_data,
            "pickup_time": pickup_ticket["time"],
            "pickup_location": pickup_ticket["location"]
        }).execute()
    except Exception as e:
        print(f"Error saving basket to Supabase: {e}")

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

# 5. Dynamic System Prompt with Allowance Math & Suggestions
def build_system_prompt():
    inventory_data = get_pantry_inventory()
    basket = st.session_state.get("basket", {})
    
    # Calculate exactly how many items they have left in each department
    category_counts = {}
    for item_name, details in basket.items():
        cat = details['category']
        category_counts[cat] = category_counts.get(cat, 0) + details['quantity']
        
    available_categories = {item['category'] for item in inventory_data}
    allowances = []
    for cat in available_categories:
        used = category_counts.get(cat, 0)
        remaining = max(0, 3 - used)
        allowances.append(f"- {cat}: {remaining} items remaining")
        
    allowance_text = "\n".join(allowances)
    basket_summary = str(basket) if basket else "Empty"

    prompt = (
        "You are Monique, the gracious, eloquent, and deeply caring Floor Manager for Cultivating Community, a community food pantry in Washington, D.C. "
        "Your voice and tone embody the poise, warmth, and inspiring elegance of Michelle Obama—welcoming, dignified, articulate, and deeply supportive of our community.\n\n"
        "LIVE PANTRY INVENTORY DATABASE:\n"
        f"{inventory_data}\n\n"
        "CURRENT VISITOR BASKET:\n"
        f"{basket_summary}\n\n"
        "REMAINING DEPARTMENT ALLOWANCES (Max 3 per department):\n"
        f"{allowance_text}\n\n"
        "NON-PROFIT OPERATIONAL RULES:\n"
        "1. EVERYTHING IS 100% FREE: Never discuss buying, selling, prices, or payments.\n"
        "2. SUGGESTIONS & LIMITS: If the visitor asks what they can add or what is available, look at their 'REMAINING DEPARTMENT ALLOWANCES'. Politely inform them if any category is full (0 remaining), and suggest 2 or 3 specific items from the inventory that belong to departments where they still have space.\n"
        "3. ACCURATE STOCK: Only suggest items that are currently in the live inventory database.\n"
        "4. ABSOLUTE PRIVACY: NEVER ask for names, IDs, phone numbers, or addresses.\n"
        "5. DYNAMIC LANGUAGE: Respond in the EXACT SAME language the visitor uses.\n"
        "6. CONCISE & WARM: Keep responses to 2-3 polished sentences. Direct visitors to check their basket on the sidebar and tap 'Claim Ration' when finished."
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
    save_basket_to_supabase(st.session_state.basket, ticket)
    st.session_state.pickup_ticket = ticket
    st.session_state.claim_success = True
    st.session_state.basket = {}

# Advanced NLP Item Parsing & Limit Detection
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
            current_qty = st.session_state.basket.get(iname, {}).get("quantity", 0)
            cat_count = sum(d['quantity'] for d in st.session_state.basket.values() if d['category'] == cat)
            
            if cat_count < 3 and current_qty < 3:
                st.session_state.basket[iname] = {"category": cat, "quantity": current_qty + 1}
                added.append(iname)
            else:
                rejected.append({"name": iname, "category": cat})
                
    return added, rejected

# 8. Main UI  
st.title("Community Pantry Kiosk")

inventory_items = get_pantry_inventory()
total_quantity = sum([item.get('quantity', 0) for item in inventory_items])
st.metric(label="Total Items Available Today", value=total_quantity)

# Sidebar Basket Inspector
st.sidebar.markdown("### 🛒 Your Custom Basket")
if st.session_state.basket:
    for item_name, details in st.session_state.basket.items():
        st.sidebar.text(f"• {item_name} (Qty: {details['quantity']})")
    if st.sidebar.button("Clear Basket"):
        st.session_state.basket = {}
        st.rerun()
else:
    st.sidebar.info("Your basket is empty. Let Monique know what you would like to select!")

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

    for msg in st.session_state.messages:
        if msg["role"] != "system":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    st.markdown("### 💬 Talk or Type to Monique")
    
    user_input_text = ""

    audio_value = st.audio_input("🎤 Tap microphone to talk", key=f"mic_{st.session_state.audio_key}")
    chat_text = st.chat_input("✨ Or type your request here...")

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
        st.session_state.messages.append({"role": "user", "content": user_input_text})
        
        added_items, rejected_items = check_and_auto_add_cart(user_input_text, inventory_items)
        
        if rejected_items:
            rej_names = [r["name"] for r in rejected_items]
            rej_cat = rejected_items[0]["category"]
            sys_note = (
                f"[SYSTEM ALERT: The visitor tried to add {', '.join(rej_names)}, but they already have 3 items in the '{rej_cat}' department. "
                f"You MUST explicitly tell them they cannot add any more {rej_cat} items, but warmly suggest they choose items from other available departments.]"
            )
            st.session_state.messages.append({"role": "system", "content": sys_note})
            
        with st.chat_message("user"):
            st.markdown(user_input_text)
            
        with st.chat_message("assistant"):
            with st.spinner("Monique is reviewing your basket..."):
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
                    
                    if not response_text or not response_text.strip():
                        response_text = "Your basket is looking wonderful. May I suggest adding some hearty grains or fresh greens to complete your selection?"
                        
                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    st.session_state.speak_greeting = response_text
                    
                except Exception as e:
                    st.error(f"Connection issue: {e}")
                    
        st.session_state.audio_key += 1
        st.rerun()

    st.divider()

    st.button("✅ Claim Ration", use_container_width=True, type="primary", on_click=process_claim, disabled=(total_quantity <= 0 or not st.session_state.basket))

    if not st.session_state.basket:
        st.warning("Add at least one item to your basket before claiming your ration.")

    if total_quantity <= 0:
        st.error("Daily rations are currently empty for today.")
