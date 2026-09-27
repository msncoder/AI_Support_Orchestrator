import os
from typing import TypedDict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

# ==========================================
# 1. Initialize Model
# ==========================================
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite"
)

# ==========================================
# 2. Define State Schema (TypedDict)
# ==========================================
class AgentState(TypedDict):
    ticket_id: str
    customer_email: str  # NEW: Added to target the specific user
    issue: str
    db_findings: Optional[str]
    plan: Optional[str]
    next_node: str
    status: str

# ==========================================
# 3. Define Agent Nodes
# ==========================================
def supervisor_node(state: AgentState) -> AgentState:
    """Decides the next step and formulates action plans based on findings."""
    print("🤖 [Supervisor]: Analyzing the ticket...")
    
    if not state.get("db_findings"):
        print("🤖 [Supervisor]: Need more context. Routing to DB Analyst.")
        return {"next_node": "db_analyst_node"}
    
    prompt = f"""
    User Issue: {state['issue']}
    Database Findings: {state['db_findings']}
    
    Based on the above, create a short, actionable plan to resolve the issue using a backend API.
    If the Payment is 'Captured' but Order is 'Failed' or 'Null', recommend hitting the POST /api/refund endpoint.
    Provide a concise plan (1-2 sentences).
    """
    
    # ---------------------------------------------
    # BULLETPROOF LLM CALL & CONTENT EXTRACTION
    # ---------------------------------------------
    try:
        response = gemini_llm.invoke([
            SystemMessage(content="You are an expert AI support orchestrator."), 
            HumanMessage(content=prompt)
        ])
        
        # Safely extract text from the response
        if isinstance(response.content, str):
            plan = response.content.strip()
        elif isinstance(response.content, list):
            # Agar Gemini list return kare toh pehla item uthao
            plan = str(response.content[0]).strip()
        else:
            plan = str(response.content).strip()
            
    except Exception as e:
        print(f"❌ [Supervisor LLM Error]: {e}")
        plan = "Error: Could not generate plan due to LLM failure."
    # ---------------------------------------------

    print(f"🤖 [Supervisor]: Plan Formulated -> {plan}")
    
    return {"plan": plan, "next_node": "action_agent_node"}

def db_analyst_node(state: AgentState) -> AgentState:
    """Performs a REAL database query to the E-commerce DB."""
    email = state.get("customer_email")
    print(f"🔍 [DB Analyst]: Connecting to DB to investigate email: {email}")
    
    db_url = os.getenv("ECOMMERCE_DB_URL")
    if not db_url:
        return {"db_findings": "Error: Database URL not found in .env", "next_node": "supervisor_node"}

    try:
        # Connect to PostgreSQL
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Query the latest transaction for this user
            query = text("""
                SELECT transaction_id, amount, payment_status, order_status, error_log 
                FROM ecommerce_transactions 
                WHERE customer_email = :email 
                ORDER BY transaction_date DESC LIMIT 1
            """)
            result = conn.execute(query, {"email": email}).fetchone()
            
            if result:
                # result -> (1, 150.00, 'Captured', 'Failed', '504 Gateway Timeout...')
                findings = f"Found Transaction ID {result[0]}: Amount ${result[1]}, Payment Status: '{result[2]}', Order Status: '{result[3]}', Error Log: '{result[4]}'."
            else:
                findings = "No transaction records found for this email."
                
    except Exception as e:
        findings = f"Database query failed due to error: {str(e)}"
        
    print(f"🔍 [DB Analyst]: Findings retrieved -> {findings}")
    
    return {"db_findings": findings, "next_node": "supervisor_node"}

def action_agent_node(state: AgentState) -> AgentState:
    """Executes the approved plan by updating the DB (simulating backend API action)."""
    print("⚡ [Action Agent]: HITL Approved! Executing the plan in Database...")
    email = state.get("customer_email")
    db_url = os.getenv("ECOMMERCE_DB_URL")
    
    if not email:
        print("❌ [Action Agent]: ERROR! 'customer_email' state mein nahi mili.")
        return {"status": "Failed - No Email Provided", "next_node": "END"}
    
    if db_url and email:
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(db_url)
            
            # 'begin()' use karne se transaction automatically commit (save) ho jati hai
            with engine.begin() as conn:
                update_query = text("""
                    UPDATE ecommerce_transactions 
                    SET payment_status = 'Refunded (By AI)', 
                        order_status = 'Resolved'
                    WHERE customer_email = :email
                """)
                # Query execute karo aur result save karo
                result = conn.execute(update_query, {"email": email})
                
                print(f"⚡ [Action Agent]: SUCCESS! {result.rowcount} rows updated in DB for {email}.")
                
                # Agar rowcount 0 hai, iska matlab DB mein wo email nahi mili
                if result.rowcount == 0:
                    print("⚠️ [Action Agent]: Warning! Query chali par koi record update nahi hua. Email check karein.")

        except Exception as e:
            print(f"❌ [Action Agent]: Error updating DB: {e}")
            return {"status": f"Failed at DB Update: {e}", "next_node": "END"}
            
    return {"status": "Resolved", "next_node": "END"}

def router(state: AgentState) -> str:
    """Reads the 'next_node' from state and routes the graph."""
    if state.get("next_node") == "END":
        return END
    return state["next_node"]

# ==========================================
# 5. Build and Compile the Graph
# ==========================================
workflow = StateGraph(AgentState)

workflow.add_node("supervisor_node", supervisor_node)
workflow.add_node("db_analyst_node", db_analyst_node)
workflow.add_node("action_agent_node", action_agent_node)

workflow.add_edge(START, "supervisor_node")
workflow.add_conditional_edges(
    "supervisor_node",
    router,
    {"db_analyst_node": "db_analyst_node", "action_agent_node": "action_agent_node"}
)
workflow.add_edge("db_analyst_node", "supervisor_node")
workflow.add_edge("action_agent_node", END)

memory = MemorySaver()

# THE APP IMPORTED BY STREAMLIT
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["action_agent_node"]
)

# ==========================================
# 6. Simulate Execution (CLI Testing)
# ==========================================
if __name__ == "__main__":
    thread_config = {"configurable": {"thread_id": "TICKET_1001"}}
    
    # Passing the exact email we inserted in the DB that has an anomaly
    initial_state = {
        "ticket_id": "TICKET_1001",
        "customer_email": "user@example.com",
        "issue": "My money was deducted but I didn't get any order confirmation on my dashboard.",
        "db_findings": None,
        "plan": None,
        "status": "Investigating"
    }
    
    print("\n--- 🚀 TRIGGER: ENGINEER CLICKS 'INVESTIGATE' ---\n")
    for event in app.stream(initial_state, thread_config):
        pass 
    
    print("\n--- ⏸️ SYSTEM PAUSED (interrupt_before hit) ---\n")
    current_state = app.get_state(thread_config)
    print("📬 [Dashboard UI]: AI Investigation Complete. Waiting for Approval.")
    print(f"📝 Proposed Plan: {current_state.values.get('plan')}")
    
    input("\n👨‍💻 Engineer: Press Enter to click 'Approve Action'...")
    
    print("\n--- ▶️ RESUMING: ENGINEER APPROVED ---\n")
    for event in app.stream(None, thread_config):
        pass

    final_state = app.get_state(thread_config).values
    print(f"\n✅ Final Ticket Status: {final_state.get('status')}")