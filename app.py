import os
import re
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta

# ==========================================
# 1. PAGE CONFIGURATION & CREDENTIALS
# ==========================================
st.set_page_config(
    page_title="Cultivating Community — Floor Manager Kiosk", 
    page_icon="🍲", 
    layout="wide"
)

SUPABASE_URL = "https://qvmabwhlqzngzncawlue.supabase.co"
SUPABASE_KEY = "sb_publishable_vlLsuD4DIgnL2fqpbr6QLQ_VsYWsAqm"
GROQ_API_KEY = "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"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# ==========================================
# 2. CACHED DATABASE OPERATIONS
# ==========================================
@st.cache_data(ttl=20)
def get_pantry_inventory():
    try:
        response = supabase.table("inventory").select("*").execute()
        return response.data
    except Exception as e:
        return []

@st.cache_data(ttl=10)
def get_all_baskets():
    try:
        response = supabase.table("baskets").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        try:
            response = supabase.table("baskets").select("*").execute()
            return response.data
        except:
            return []

def update_inventory_stock(item_id, new_quantity):
    try:
        supabase.table("inventory").update({"quantity": new_quantity}).eq("id", item_id).execute()
        st.cache_data.clear()
    except Exception as e:
        print(f"Error updating stock: {e}")

def save_basket_to_supabase(basket_data, pickup_ticket):
    try:
        response = supabase.table("baskets").insert({
            "items": basket_data,
            "pickup_time": pickup_ticket["time"],
            "pickup_location": pickup_ticket["location"]
        }).execute()
        
        ticket_id = response.data[0].get('id') if response.data else None

        inventory_items = get_pantry_inventory()
        for item_name, details in basket_data.items():
            claimed_qty = details.get('quantity', 0)
            for inv in inventory_items:
                if inv['item_name'].lower() == item_name.lower():
                    current_stock = inv['quantity']
                    new_stock = max(0, current_stock - claimed_qty)
                    update_inventory_stock(inv['id'], new_stock)

        st.cache_data.clear()
        return ticket_id
    except Exception as e:
        print(f"Error saving basket or decrementing stock: {e}")
    return None

# ==========================================
# 3. TEXT-TO-SPEECH AUDIO INJECTION
# ==========================================
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

# ==========================================
# 4. MONIQUE AI SYSTEM PROMPT BUILDER
# ==========================================
def build_system_prompt(transaction_report=""):
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
        allowances.append(f"- {cat}: {remaining} items remaining (Used {used}/3)")
        
    allowance_text = "\n".join(allowances)
    basket_summary = str(basket) if basket else "Empty"

    transaction_section = f"\n\nIMMEDIATE ACTION REPORT (What just happened on this turn):\n{transaction_report}\n\n" if transaction_report else ""

    prompt = (
        "You are Monique, the gracious, eloquent, and deeply caring Floor Manager for Cultivating Community, a community food pantry in Washington, D.C. "
        "Your voice and tone embody the poise, warmth, and inspiring elegance of Michelle Obama—welcoming, dignified, articulate, and deeply supportive of our community.\n\n"
        "LIVE PANTRY INVENTORY DATABASE:\n"
        f"{inventory_data}\n\n"
        "CURRENT VISITOR BASKET:\n"
        f"{basket_summary}\n\n"
        "REMAINING DEPARTMENT ALLOWANCES (Max 3 per department):\n"
        f"{allowance_text}"
        f"{transaction_section}"
        "CONVERSATIONAL RULES:\n"
        "1. NEVER AUTO-ADD OR MODIFY BASKET ON GENERAL QUESTIONS: If the visitor asks 'What else can I add?', 'What's available?', or 'What do you have?', DO NOT modify or add items to their basket. Review their current basket, check remaining department allowances, and verbally suggest available items from departments where they still have space.\n"
        "2. ACKNOWLEDGE EXPLICIT ADDITIONS: If the visitor explicitly asks to add an item, confirm it. If a department is full (0 remaining), gently let them know.\n"
        "3. DELIVERY INQUIRIES: If asked about delivery, inform them that specialized delivery within Washington, D.C. borders is available for $30 for elderly or mobility-impaired residents who cannot travel.\n"
        "4. EVERYTHING IS FREE & PRIVATE: Food is 100% free (only specialized delivery has a $30 courier fee). Never ask for personal names, IDs, or home addresses in chat.\n"
        "5. WARM & CONCISE: Keep responses to 2-3 warm sentences. Direct them to tap 'Claim Ration' when finished."
    )
    return prompt

# ==========================================
# 5. STATE MANAGEMENT INITIALIZATION
# ==========================================
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
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "financial_ledger" not in st.session_state:
    st.session_state.financial_ledger = [
        {"type": "Inflow", "category": "Grant", "source": "D.C. Community Health Grant", "amount": 25000.0, "date": "2026-10-01"},
        {"type": "Inflow", "category": "Donation", "source": "Anonymous Patron", "amount": 5000.0, "date": "2026-10-05"},
        {"type": "Outflow", "category": "Operations", "source": "Hub Rental & Utilities", "amount": 4000.0, "date": "2026-10-10"},
        {"type": "Outflow", "category": "Logistics", "source": "Delivery Fleet Fuel & Insurance", "amount": 2000.0, "date": "2026-10-12"}
    ]
if "rescue_logs" not in st.session_state:
    st.session_state.rescue_logs = [
        {"donor": "Call Your Mother Bakery", "items": "25 Bagel Sleeves & Artisan Breads", "volunteer": "Andrew", "date": "2026-10-16"}
    ]

# ==========================================
# 6. CALLBACKS & NLP PARSING
# ==========================================
def start_session():
    st.session_state.session_active = True
    greeting = "Welcome to Cultivating Community. You are welcome to select up to 3 items from each of our food departments today—how may I assist you with your basket?"
    st.session_state.messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "assistant", "content": greeting}
    ]
    st.session_state.speak_greeting = greeting  

def process_claim(is_delivery=False, dc_zip=""):
    pickup_time = (datetime.now() + timedelta(minutes=30)).strftime("%I:%M %p")
    location_str = "Cultivating Community Pickup Hub (Dandelion Collective)"
    
    if is_delivery:
        pickup_time = "Scheduled DC Courier Delivery (Today)"
        location_str = f"Delivered within Washington, D.C. (ZIP: {dc_zip}) - Fee: $30"

    ticket = {
        "time": pickup_time,
        "location": location_str,
        "is_delivery": is_delivery
    }
    
    basket_snapshot = st.session_state.basket.copy()
    ticket_id = save_basket_to_supabase(basket_snapshot, ticket)
    ticket["id"] = ticket_id if ticket_id else "ANON-PASS"
    st.session_state.pickup_ticket = ticket
    st.session_state.claim_success = True
    st.session_state.basket = {}
    
    if is_delivery:
        closing_speech = f"Please scan the QR code for your delivery ticket. Your specialized delivery within Washington D.C. has a $30 fee and is scheduled for today. Thank you for shopping with us!"
    else:
        closing_speech = f"Please scan the QR code for your anonymous ticket, and your pickup time is {ticket['time']} at Cultivating Community. Thank you for shopping with us. Hope to see you soon."
        
    st.session_state.speak_greeting = closing_speech

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
    
    general_inquiry_phrases = ["what else", "what can i add", "what do you have", "what's available", "what is available", "show me"]
    if any(phrase in text_lower for phrase in general_inquiry_phrases):
        return [], []

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
                added.append({"name": iname, "qty": add_amount, "category": cat})
                if req_qty > add_amount:
                    rejected.append({"name": iname, "category": cat, "reason": "limit_reached"})
            else:
                rejected.append({"name": iname, "category": cat, "reason": "limit_reached"})
                
    return added, rejected

# ==========================================
# 7. MAIN UI LAYOUT & SIDEBAR
# ==========================================
st.title("🍲 Cultivating Community — Floor Manager Kiosk")

inventory_items = get_pantry_inventory()
total_quantity = sum([item.get('quantity', 0) for item in inventory_items])

with st.sidebar:
    st.markdown("### 🌐 Accessibility & Language")
    selected_lang = st.selectbox("Select Language:", ["English", "Español (Spanish)", "አማርኛ (Amharic)", "Français (French)", "Tiếng Việt (Vietnamese)"])
    st.markdown("---")

    st.markdown("### 🔐 Portal Navigation")
    portal_mode = st.radio("Select View:", ["🛍️ Shopper Kiosk", "🛠️ Admin Portal (Volunteers)"])
    st.markdown("---")

    if portal_mode == "🛠️ Admin Portal (Volunteers)":
        st.markdown("### 🔒 Staff Sign-In")
        if not st.session_state.admin_logged_in:
            admin_user = st.text_input("Username")
            admin_pass = st.text_input("Password", type="password")
            if st.button("Sign In", use_container_width=True):
                if admin_user == "andrew" and admin_pass == "dandelion2026":
                    st.session_state.admin_logged_in = True
                    st.success("Successfully logged in!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        else:
            st.success("Signed in as Administrator")
            if st.button("Sign Out", use_container_width=True):
                st.session_state.admin_logged_in = False
                st.rerun()

    if portal_mode == "🛍️ Shopper Kiosk" or not st.session_state.admin_logged_in:
        st.markdown("### 🛒 Your Custom Basket")
        if st.session_state.basket:
            grouped_basket = {}
            for item_name, details in st.session_state.basket.items():
                cat = details['category']
                if cat not in grouped_basket:
                    grouped_basket[cat] = []
                grouped_basket[cat].append((item_name, details['quantity']))
                
            for cat, items in grouped_basket.items():
                st.markdown(f"**📂 {cat}**")
                for item_name, qty in items:
                    st.text(f"  • {item_name} (Qty: {qty})")
                    
            st.markdown("")
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
            st.markdown(f"🕒 **Fulfillment:** {ticket['time']}")
            st.markdown(f"📍 **Details:** {ticket['location']}")
            
            qr_data = f"Cultivating-Community-Ticket-{ticket['id']}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={qr_data}"
            st.image(qr_url, caption=f"Scan to Verify (ID: {ticket['id']})", width=180)
            st.caption("🔒 100% Anonymous: No personal information collected.")

            if st.button("Start New Visit", use_container_width=True):
                st.session_state.claim_success = False
                st.session_state.pickup_ticket = None
                st.session_state.session_active = False
                st.session_state.messages = []
                st.rerun()
        else:
            st.markdown("### 🚚 Fulfillment Options")
            fulfillment_type = st.radio("Choose Mode:", ["Pickup (Free)", "Delivery within DC ($30 Fee)"])
            
            dc_zip_input = ""
            if fulfillment_type == "Delivery within DC ($30 Fee)":
                st.info("Special circumstance delivery is available for elderly residents or individuals unable to walk, strictly within Washington, D.C. borders.")
                dc_zip_input = st.text_input("Enter D.C. Zip Code (e.g., 20020):")
                
            if st.button("✅ Confirm & Claim Ration", use_container_width=True, type="primary", disabled=(total_quantity <= 0 or not st.session_state.basket)):
                if fulfillment_type == "Delivery within DC ($30 Fee)":
                    if not dc_zip_input.strip():
                        st.error("Please enter a valid D.C. zip code for delivery.")
                    else:
                        process_claim(is_delivery=True, dc_zip=dc_zip_input)
                        st.rerun()
                else:
                    process_claim(is_delivery=False)
                    st.rerun()

# ==========================================
# 8. ADMIN PORTAL VIEW
# ==========================================
if portal_mode == "🛠️ Admin Portal (Volunteers)" and st.session_state.admin_logged_in:
    st.header("🛠️ Cultivating Community — Admin Dashboard")
    st.markdown("Welcome, team! Monitor live orders, check department inventory, coordinate food rescue, track universal financials, and review real-time AI strategic recommendations.")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📦 Live Inventory", "📋 Placed Orders", "⚙️ Update Stock", "🤝 Food Rescue & Ledger", "🧠 Autonomous AI Grant & Funding Strategist"])
    
    with tab1:
        st.subheader("Current Stock Levels by Department")
        if not inventory_items:
            st.info("No inventory items found.")
        else:
            grouped_inv = {}
            for item in inventory_items:
                cat = item['category']
                if cat not in grouped_inv:
                    grouped_inv[cat] = []
                grouped_inv[cat].append(item)
                
            for cat, items in grouped_inv.items():
                st.markdown(f"### 📂 {cat}")
                for item in items:
                    cols = st.columns([3, 2])
                    cols[0].markdown(f"• **{item['item_name']}**")
                    cols[1].markdown(f"Stock Left: **{item['quantity']} {item['unit']}**")
                st.divider()
                
    with tab2:
        st.subheader("Recent Anonymous Basket Orders & Deliveries")
        baskets = get_all_baskets()
        if not baskets:
            st.info("No orders placed yet.")
        else:
            for b in baskets:
                with st.container(border=True):
                    cols = st.columns(2)
                    cols[0].markdown(f"**Order ID:** `{b.get('id')}`")
                    cols[1].markdown(f"🕒 **Fulfillment:** {b.get('pickup_time')}")
                    st.caption(f"📍 **Location/Type:** {b.get('pickup_location')}")
                    st.markdown("**Items Claimed:**")
                    items_dict = b.get('items', {})
                    for item_name, details in items_dict.items():
                        st.text(f"  • {item_name} (Qty: {details.get('quantity', 1)})")

    with tab3:
        st.subheader("Daily Stock Reset & Updates")
        if not inventory_items:
            st.info("No inventory items found to update.")
        else:
            with st.form("inventory_update_form"):
                updated_quantities = {}
                for item in inventory_items:
                    new_val = st.number_input(
                        label=f"{item['item_name']} ({item['category']}) - Current: {item['quantity']} {item['unit']}",
                        min_value=0,
                        value=int(item['quantity']),
                        key=f"update_stock_{item['id']}"
                    )
                    updated_quantities[item['id']] = new_val
                
                submit_updates = st.form_submit_button("💾 Save Daily Stock Updates", type="primary")
                if submit_updates:
                    for item_id, qval in updated_quantities.items():
                        update_inventory_stock(item_id, qval)
                    st.success("✅ Daily inventory successfully updated!")
                    st.rerun()

    with tab4:
        st.subheader("🤝 Surplus Food Rescue Log")
        with st.form("rescue_form_easy"):
            col_r1, col_r2 = st.columns(2)
            donor_source = col_r1.selectbox("Donor / Bakery Source", ["Call Your Mother Bakery", "Trader Joe's Surplus", "Local Farm Drop", "Other Community Partner"])
            volunteer_duty = col_r2.text_input("Volunteer / Coordinator on Duty", value="Andrew")
            
            rescue_summary = st.text_input("Items & Quantities (e.g., 30 Bagel Sleeves, 15 Produce Boxes)")
            submit_quick_rescue = st.form_submit_button("📥 Log Food Rescue Drop", type="primary")
            if submit_quick_rescue and rescue_summary:
                st.session_state.rescue_logs.insert(0, {"donor": donor_source, "items": rescue_summary, "volunteer": volunteer_duty, "date": datetime.now().strftime("%Y-%m-%d")})
                st.success(f"Successfully logged rescue drop from {donor_source}!")

        if st.session_state.rescue_logs:
            st.markdown("**Recent Food Rescues:**")
            for log in st.session_state.rescue_logs:
                st.text(f"• [{log['date']}] {log['donor']}: {log['items']} (Logged by {log['volunteer']})")

        st.markdown("---")
        st.subheader("📊 Universal Financial Ledger (Inflows & Outflows)")
        total_inflow = sum(item['amount'] for item in st.session_state.financial_ledger if item['type'] == 'Inflow')
        total_outflow = sum(item['amount'] for item in st.session_state.financial_ledger if item['type'] == 'Outflow')
        net_balance = total_inflow - total_outflow

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Inflows (Grants/Donations)", f"${total_inflow:,.2f}")
        col_m2.metric("Total Outflows (Expenses)", f"${total_outflow:,.2f}")
        col_m3.metric("Net Operating Balance", f"${net_balance:,.2f}")

        st.markdown("---")
        st.markdown("#### Add New Transaction")
        with st.form("ledger_form"):
            col_l1, col_l2, col_l3, col_l4 = st.columns(4)
            tx_type = col_l1.selectbox("Type", ["Inflow", "Outflow"])
            tx_cat = col_l2.selectbox("Category", ["Grant", "Donation", "Delivery Fee", "Operations", "Logistics", "Store Fund Setup", "Other"])
            tx_source = col_l3.text_input("Source / Description")
            tx_amount = col_l4.number_input("Amount ($)", min_value=0.0, step=50.0)
            
            submit_tx = st.form_submit_button("➕ Record Transaction", type="primary")
            if submit_tx and tx_source:
                st.session_state.financial_ledger.insert(0, {
                    "type": tx_type,
                    "category": tx_cat,
                    "source": tx_source,
                    "amount": tx_amount,
                    "date": datetime.now().strftime("%Y-%m-%d")
                })
                st.success("Transaction recorded successfully!")
                st.rerun()

        st.markdown("#### Transaction History")
        for tx in st.session_state.financial_ledger:
            color_emoji = "🟢" if tx['type'] == 'Inflow' else "🔴"
            sign = "+" if tx['type'] == 'Inflow' else "-"
            st.text(f"{color_emoji} [{tx['date']}] {tx['type']} ({tx['category']}) - {tx['source']}: {sign}${tx['amount']:,.2f}")

    with tab5:
        st.subheader("🧠 Autonomous AI Grant & Funding Strategist")
        st.markdown("Your AI strategist continuously monitors live inventory levels, recent basket activity, and financial ledgers to provide daily recommendations on how to scale the nonprofit and fund the Wards 7 or 8 walk-in dignity grocery store.")

        if "cached_ai_recommendation" not in st.session_state:
            with st.spinner("AI Strategist is analyzing live dashboard metrics and D.C. community food security data..."):
                try:
                    total_inflow_calc = sum(item['amount'] for item in st.session_state.financial_ledger if item['type'] == 'Inflow')
                    total_outflow_calc = sum(item['amount'] for item in st.session_state.financial_ledger if item['type'] == 'Outflow')
                    
                    prompt_payload = (
                        f"Analyze our current dashboard metrics for Cultivating Community in Washington D.C.:\n"
                        f"- Total Inflows: ${total_inflow_calc:,.2f}\n"
                        f"- Total Outflows: ${total_outflow_calc:,.2f}\n"
                        f"- Live Inventory: {inventory_items}\n"
                        f"Provide a daily strategic action plan to advance our nonprofit toward our goal of funding a Swiss-style walk-in dignity grocery store in Wards 7 or 8. "
                        f"Format your response clearly into three sections:\n"
                        f"1. **WHAT & WHY**: Specific action item and reasoning based on current data.\n"
                        f"2. **HOW**: Step-by-step execution guide.\n"
                        f"3. **WHO TO DELEGATE TO**: Recommended team member or partner role."
                    )
                    
                    res = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[
                            {"role": "system", "content": "You are an expert nonprofit financial strategist specializing in Washington D.C. community development, food security grants, and capital campaigns."},
                            {"role": "user", "content": prompt_payload}
                        ],
                        temperature=0.4,
                        max_tokens=400
                    )
                    st.session_state.cached_ai_recommendation = res.choices[0].message.content
                except Exception as e:
                    st.session_state.cached_ai_recommendation = f"Unable to fetch real-time AI recommendation at the moment: {e}"

        with st.container(border=True):
            st.markdown("### 🎯 Today's Strategic Directive")
            st.markdown(st.session_state.cached_ai_recommendation)
            
        if st.button("🔄 Refresh Strategic Analysis", use_container_width=True):
            if "cached_ai_recommendation" in st.session_state:
                del st.session_state.cached_ai_recommendation
            st.rerun()

# ==========================================
# 9. PUBLIC SHOPPER KIOSK VIEW
# ==========================================
else:
    col_grid, col_chat = st.columns([1.2, 1])

    with col_grid:
        st.markdown("### 📦 Available Pantry Inventory")
        
        dietary_filter = st.selectbox(
            "Filter by Dietary Need / Health Preference:", 
            ["All Items", "Gluten-Free", "Vegan / Vegetarian", "Halal", "Diabetic-Friendly"]
        )
        
        if not inventory_items:
            st.warning("No inventory loaded in Supabase yet.")
        else:
            filtered_inventory = []
            for item in inventory_items:
                iname = item['item_name'].lower()
                
                if dietary_filter == "Gluten-Free" and not any(k in iname for k in ['oatmeal', 'rice', 'apple', 'spinach', 'kale', 'orange', 'fruit']):
                    continue
                elif dietary_filter == "Vegan / Vegetarian" and 'beef' in iname:
                    continue
                elif dietary_filter == "Diabetic-Friendly" and any(k in iname for k in ['sugar', 'peach', 'pancake']):
                    continue
                filtered_inventory.append(item)

            if not filtered_inventory:
                st.info(f"No items currently match the filter: {dietary_filter}")
            else:
                cols = st.columns(3)
                for index, item in enumerate(filtered_inventory):
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

        st.markdown("---")
        st.info("ℹ️ **Community Dignity Note**: All fresh food, staples, and prepared meals are 100% free of charge. Specialized courier delivery is available for $30 for elderly or mobility-impaired D.C. residents.")

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
                
                report_lines = []
                if added_items:
                    added_desc = [f"{i['qty']}x {i['name']} ({i['category']})" for i in added_items]
                    report_lines.append(f"- Successfully added to basket: {', '.join(added_desc)}")
                if rejected_items:
                    rej_desc = [r['name'] for r in rejected_items]
                    report_lines.append(f"- Blocked/Rejected (Department limit of 3 reached): {', '.join(rej_desc)}")
                if not added_items and not rejected_items:
                    report_lines.append("- No items were added or modified (this was a general inquiry or advisory request).")
                    
                transaction_report = "\n".join(report_lines)
                
                with st.spinner("Monique is responding..."):
                    system_prompt = build_system_prompt(transaction_report)
                    if st.session_state.messages and st.session_state.messages[0]["role"] == "system":
                        st.session_state.messages[0]["content"] = system_prompt
                    else:
                        st.session_state.messages.insert(0, {"role": "system", "content": system_prompt})
                    
                    try:
                        completion = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=st.session_state.messages,
                            temperature=0.3,
                            max_tokens=250
                        )
                        response_text = completion.choices[0].message.content
                        
                        if not response_text or not response_text.strip():
                            response_text = "I'm here to help you find whatever you need. Let me know which department you'd like to explore next!"
                            
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                        st.session_state.speak_greeting = response_text
                        
                    except Exception as e:
                        st.error(f"Connection issue: {e}")
                            
            st.session_state.audio_key += 1
            st.rerun()
