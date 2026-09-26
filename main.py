import json
import logging
import sqlite3
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import app as graph_app
from langgraph.types import Command
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SQL Data Analyst Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    query: str
    thread_id: str

class ResumeRequest(BaseModel):
    action: str
    thread_id: str

def generate_events(input_data, thread_config):
    try:
        for event in graph_app.stream(input_data, config=thread_config):
            for node_name, state_update in event.items():
                payload = {"node": node_name}
                if "generated_sql" in state_update:
                    payload["sql"] = state_update["generated_sql"]
                if "final_answer" in state_update:
                    payload["answer"] = state_update["final_answer"]
                if "error" in state_update and state_update["error"]:
                    payload["error"] = state_update["error"]
                yield f"data: {json.dumps(payload)}\n\n"

        state = graph_app.get_state(thread_config)
        if state.next:
            interrupt_data = state.tasks[0].interrupts[0].value
            yield f"data: {json.dumps({'interrupt': interrupt_data})}\n\n"
            
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'error': 'An internal server error occurred.'})}\n\n"

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()

@app.post("/chat")
def chat(request: ChatRequest):
    logger.info(f"Starting new chat thread: {request.thread_id}")
    thread_config = {"configurable": {"thread_id": request.thread_id}}
    initial_state = {
        "messages": [HumanMessage(content=request.query)], 
        "retry_count": 0
    }
    return StreamingResponse(
        generate_events(initial_state, thread_config), 
        media_type="text/event-stream"
    )

@app.post("/resume")
def resume(request: ResumeRequest):
    logger.info(f"Resuming thread: {request.thread_id} with action: {request.action}")
    thread_config = {"configurable": {"thread_id": request.thread_id}}
    return StreamingResponse(
        generate_events(Command(resume=request.action), thread_config), 
        media_type="text/event-stream"
    )

@app.get("/schema")
def get_schema():
    try:
        conn = sqlite3.connect("chinook.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        schema = []
        for table in tables:
            table_name = table[0]
            if table_name == "sqlite_sequence": 
                continue
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = [{"name": col[1], "type": col[2]} for col in cursor.fetchall()]
            schema.append({"name": table_name, "columns": columns})
        conn.close()
        return {"tables": schema}
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return {"error": str(e)}
