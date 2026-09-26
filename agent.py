import os
import sqlite3
import logging
from typing import TypedDict, Optional, Annotated
from langchain_community.utilities import SQLDatabase
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

db = SQLDatabase.from_uri("sqlite:///chinook.db")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    schema: str
    generated_sql: Optional[str]
    sql_result: Optional[str]
    error: Optional[str]
    retry_count: int
    final_answer: Optional[str]
    needs_sql: Optional[bool]

class PlannerOutput(BaseModel):
    needs_sql: bool = Field(description="True ONLY if a SQL query must be executed to fetch data rows. False for greetings or schema inquiries.")
    direct_answer: str = Field(description="If needs_sql is False, provide the detailed response here. Otherwise, leave empty.")

PLANNER_SYS = """You are the intelligent routing agent for a digital media store SQL database assistant.
<database_schema>\n{schema_info}\n</database_schema>
RULES:
1. DATA QUERIES (needs_sql = True): If the user asks a question that requires calculating, aggregating, or fetching actual rows of data (e.g., "who is the top artist?", "total sales"), you MUST set needs_sql to True. Do NOT attempt to answer these questions directly.
2. SCHEMA INQUIRIES (needs_sql = False): If the user asks to explain the database structure, tables, or columns, use the <database_schema> to answer them directly.
3. GENERAL CHITCHAT (needs_sql = False): Respond politely and guide them back to asking about the media store data."""

SQL_GEN_SYS = """You are an expert SQLite data analyst. Generate a valid SQLite query to answer the user's latest question, considering the conversation history.
<database_schema>\n{schema}\n</database_schema>
CRITICAL CONSTRAINTS:
1. ONLY return the raw SQL query. No markdown formatting.
2. Ensure the query strictly adheres to SQLite syntax.
3. Do NOT invent tables or columns.
4. If the user asks for "top", "most", or "best", ALWAYS apply an appropriate `ORDER BY` and `LIMIT` clause.
5. NEVER generate destructive operations (INSERT, UPDATE, DELETE).
<previous_error>\n{error}\n</previous_error>
If <previous_error> is not "None", adjust your query to fix it."""

FORMATTER_SYS = """You are a professional Data Analyst presenting findings.
<sql_execution_result>\n{sql_result}\n</sql_execution_result>
<execution_error>\n{error}\n</execution_error>
INSTRUCTIONS:
1. If <execution_error> has an error, apologize and explain the technical issue politely.
2. If <sql_execution_result> has data, provide a crisp, accurate answer to the user's question based on the conversation history.
3. Format data neatly using Markdown.
4. Do NOT mention the internal SQL query unless asked. Focus on the business answer.
5. Do NOT hallucinate data."""

def planner_node(state: AgentState):
    logger.info("Executing planner_node")
    schema_info = db.get_table_info()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYS.replace("{schema_info}", schema_info)),
        MessagesPlaceholder(variable_name="messages")
    ])
    structured_llm = llm.with_structured_output(PlannerOutput)
    chain = prompt | structured_llm
    result = chain.invoke({"messages": state["messages"]})
    
    if result.needs_sql:
        return {"schema": schema_info, "needs_sql": True}
    
    return {
        "messages": [AIMessage(content=result.direct_answer)], 
        "final_answer": result.direct_answer, 
        "needs_sql": False
    }

def sql_generator_node(state: AgentState):
    logger.info("Executing sql_generator_node")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SQL_GEN_SYS),
        MessagesPlaceholder(variable_name="messages")
    ])
    error_msg = state.get("error", "") or "None"
    chain = prompt | llm
    
    response = chain.invoke({
        "schema": state["schema"],
        "error": error_msg,
        "messages": state["messages"]
    })
    clean_sql = response.content.replace("```sql", "").replace("```", "").strip()
    return {"generated_sql": clean_sql, "error": None}

def validator_node(state: AgentState):
    sql = state.get("generated_sql", "").strip().upper()
    if not sql.startswith("SELECT"): return {"error": "Safety Guardrail: Query must begin with SELECT."}
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]
    for word in forbidden:
        if word in sql.split(): return {"error": f"Safety Guardrail: Keyword '{word}' prohibited."}
    return {"error": None}

def human_approval_node(state: AgentState):
    sql = state.get("generated_sql", "")
    user_approval = interrupt(f"Generated SQL:\n{sql}\n\nDo you approve execution? (yes/no)")
    if user_approval.lower() not in ["yes", "y", "approve"]: return {"error": "User rejected this query."}
    return {"error": None}

def executor_node(state: AgentState):
    try:
        result = db.run(state["generated_sql"])
        return {"sql_result": result}
    except Exception as e:
        return {"error": str(e)}

def error_handler_node(state: AgentState):
    return {"retry_count": state.get("retry_count", 0) + 1}

def formatter_node(state: AgentState):
    logger.info("Executing formatter_node")
    prompt = ChatPromptTemplate.from_messages([
        ("system", FORMATTER_SYS),
        MessagesPlaceholder(variable_name="messages")
    ])
    chain = prompt | llm
    
    response = chain.invoke({
        "sql_result": state.get("sql_result", "None"),
        "error": state.get("error", "None"),
        "messages": state["messages"]
    })
    
    return {
        "messages": [AIMessage(content=response.content)],
        "final_answer": response.content
    }

def route_from_planner(state: AgentState):
    if state.get("needs_sql"): return "sql_generator_node"
    return END

def route_from_validator(state: AgentState):
    if state.get("error"): return "error_handler_node"
    return "human_approval_node"
    
def route_from_approval(state: AgentState):
    if state.get("error"): return "formatter_node"
    return "executor_node"

def route_from_executor(state: AgentState):
    if state.get("error"): return "error_handler_node"
    return "formatter_node"

def route_from_error_handler(state: AgentState):
    if state.get("retry_count", 0) >= 3: return END 
    return "sql_generator_node"

workflow = StateGraph(AgentState)
workflow.add_node("planner_node", planner_node)
workflow.add_node("sql_generator_node", sql_generator_node)
workflow.add_node("validator_node", validator_node)
workflow.add_node("human_approval_node", human_approval_node)
workflow.add_node("executor_node", executor_node)
workflow.add_node("error_handler_node", error_handler_node)
workflow.add_node("formatter_node", formatter_node)

workflow.set_entry_point("planner_node")
workflow.add_conditional_edges("planner_node", route_from_planner)
workflow.add_edge("sql_generator_node", "validator_node")
workflow.add_conditional_edges("validator_node", route_from_validator)
workflow.add_conditional_edges("human_approval_node", route_from_approval)
workflow.add_conditional_edges("executor_node", route_from_executor)
workflow.add_conditional_edges("error_handler_node", route_from_error_handler)
workflow.add_edge("formatter_node", END)

conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)
memory.setup()
app = workflow.compile(checkpointer=memory)
