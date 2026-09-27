import streamlit as st
import time
import random
from ai_orchestrator import app as ai_app  

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="E-Comm Admin | Support Desk", page_icon="🛍️", layout="wide")

# --- 2. CUSTOM CSS FOR STYLING ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
    }
    .ticket-box {
        border-left: 5px solid #FF4B4B;
        padding-left: 15px;
        background-color: #262730;
        padding: 20px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE ---
if "active_ticket" not in st.session_state:
    st.session_state.active_ticket = None
if "status" not in st.session_state:
    st.session_state.status = "Idle"
if "db_findings" not in st.session_state:
    st.session_state.db_findings = ""
if "plan" not in st.session_state:
    st.session_state.plan = ""

# --- 4. SIDEBAR (NAVIGATION) ---
with st.sidebar:
    st.title("🛍️ ShopAdmin")
    st.divider()
    st.markdown("📦 **Orders**")
    st.markdown("👥 **Customers**")
    st.markdown("📈 **Analytics**")
    st.markdown("🎧 **Support Desk** 🔴") 
    st.markdown("⚙️ **Settings**")
    st.divider()
    st.caption("Logged in as: Saad (L2 Support)")

# --- 5. MAIN HEADER & KPIs ---
st.title("🎧 Support Desk (AI Assisted)")
st.markdown("Manage customer escalations and approve AI workflows.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Open Tickets", "12", "+2")
col2.metric("Avg Resolution Time", "1.4m", "-0.3m")
col3.metric("AI Success Rate", "94%", "+2%")
col4.metric("Pending Approvals", "1", "-1")
st.divider()

# --- 6. TICKET CREATION AREA ---
col_form, col_view = st.columns([1, 1.5])

with col_form:
    st.subheader("📝 Create New Ticket")
    with st.form("ticket_form"):
        customer_email = st.text_input("Customer Email", "user@example.com")
        issue_text = st.text_area("Issue Description", "Paisa deduct ho gaya hai bank se, lekin dashboard par order zero dikha raha hai. Please help!")
        submitted = st.form_submit_button("Generate Ticket", type="primary")
        
        if submitted:
            st.session_state.active_ticket = f"TCK-{random.randint(1000, 9999)}"
            st.session_state.customer_email = customer_email
            st.session_state.issue_text = issue_text
            st.session_state.status = "Open"
            st.rerun()

# --- 7. TICKET ACTION DESK ---
with col_view:
    st.subheader("🎯 Active Workspace")
    
    if st.session_state.active_ticket is None:
        st.info("No active ticket selected. Please create or select a ticket from the left.")
    else:
        # LangGraph Memory ke liye Thread ID (Is ticket ke liye unique hoga)
        thread_config = {"configurable": {"thread_id": st.session_state.active_ticket}}
        
        st.markdown(f"""
        <div class="ticket-box">
            <h4>Ticket ID: {st.session_state.active_ticket}</h4>
            <p><b>Customer:</b> {st.session_state.customer_email}</p>
            <p><b>Issue:</b> <i>"{st.session_state.issue_text}"</i></p>
        </div>
        <br>
        """, unsafe_allow_html=True)
        
        # --- STATE: OPEN ---
        if st.session_state.status == "Open":
            if st.button("🤖 Investigate via AI Swarm", use_container_width=True):
                st.session_state.status = "Investigating"
                st.rerun()
                
        # --- STATE: INVESTIGATING (CONNECTING TO LANGGRAPH) ---
        elif st.session_state.status == "Investigating":
            
            # YAHAN INITIAL STATE PASS HO RAHI HAI AGENT KO
            initial_state = {
                "ticket_id": st.session_state.active_ticket,
                "customer_email": st.session_state.customer_email,
                "issue": st.session_state.issue_text,
                "db_findings": None,
                "plan": None,
                "next_node": "",
                "status": "Investigating"
            }
            
            with st.status("AI Agents are investigating the issue...", expanded=True) as status:
                st.write("⏳ Sending context to LangGraph Swarm...")
                
                # GRAPH RUN KARENGE JAB TAK PAUSE (interrupt_before) NA HO JAYE
                for event in ai_app.stream(initial_state, thread_config):
                    if "supervisor_node" in event:
                        st.write("🧠 [Supervisor]: Analyzing context and routing...")
                    elif "db_analyst_node" in event:
                        st.write(f"🔍 [DB Analyst]: Querying PostgreSQL for {st.session_state.customer_email}...")
                
                status.update(label="Investigation Complete! Awaiting Human Approval.", state="complete", expanded=False)
            
            # PAUSED STATE SE REAL DATA NIKAL RAHE HAIN
            current_state = ai_app.get_state(thread_config).values
            st.session_state.db_findings = current_state.get("db_findings", "No DB Data")
            st.session_state.plan = current_state.get("plan", "No Plan")
            
            st.session_state.status = "Pending Approval"
            st.rerun()
            
        # --- STATE: PENDING APPROVAL (HITL) ---
        elif st.session_state.status == "Pending Approval":
            st.warning("⚠️ **Human Approval Required**")
            with st.expander("📊 AI Findings & Plan (Live from DB)", expanded=True):
                # AB DUMMY NAHI, REAL DATABASE FINDINGS SHOW HONGI
                st.markdown(f"**Database Findings:**\n> {st.session_state.db_findings}")
                st.markdown(f"**Action Plan:**\n> `{st.session_state.plan}`")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
                    with st.spinner("Executing Database Update..."):
                        # RESUME THE GRAPH - Yahan Action Agent DB update karega
                        for event in ai_app.stream(None, thread_config):
                            pass
                        
                    st.session_state.status = "Resolved"
                    st.rerun()
            with c2:
                if st.button("❌ Escalate", use_container_width=True):
                    st.session_state.status = "Escalated"
                    st.rerun()
                    
        # --- STATE: RESOLVED ---
        elif st.session_state.status == "Resolved":
            st.success("🎉 Resolution executed successfully! Database updated.")
            if st.button("Clear Workspace", use_container_width=True):
                st.session_state.active_ticket = None
                st.session_state.status = "Idle"
                st.rerun()