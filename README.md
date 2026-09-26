# 🤖 SQL Data Analyst Agent

An enterprise-grade, autonomous SQL Data Analyst powered by **LangGraph**, **FastAPI**, and **OpenAI**. This agent interacts with a SQLite database, translates natural language into complex SQL queries, features a Human-in-the-Loop (HITL) safety mechanism, and autonomously self-corrects execution errors.

---

## ✨ Key Features

* **🧠 Conversational Memory:** Maintains context across multi-turn chats (e.g., "What is the top track?" -> "Is it the cheapest?").
* **🛡️ Human-in-the-Loop (HITL):** Pauses execution to require explicit human approval before running SQL against the database.
* **🔄 Autonomous Self-Correction:** Catches raw SQL execution errors and loops back to the LLM to debug and rewrite its own queries.
* **🚦 Intelligent Routing:** Uses structured output to classify user intent. Non-data questions (chitchat/schema explanations) bypass the SQL engine entirely to save tokens and time.
* **🖥️ Streaming UI Workspace:** A vanilla JS/HTML/CSS frontend utilizing Server-Sent Events (SSE) to display agent thought-processes and interactive database schema exploration in real-time.

## 🏗️ Architecture

This project is built using a **LangGraph State Machine** consisting of the following nodes:
1. `planner_node`: Fetches schema and routes the prompt based on intent.
2. `sql_generator_node`: Writes strict, optimized SQL.
3. `validator_node`: Python-based static analysis to block destructive keywords (`DROP`, `DELETE`).
4. `human_approval_node`: Graph interrupt for frontend UI approval.
5. `executor_node`: Runs the query against the database.
6. `error_handler_node`: Catches execution errors and manages the retry counter loop.
7. `formatter_node`: Converts raw SQL data dumps into polished business insights.

Persistent state is maintained using `SqliteSaver` via the LangGraph checkpointer API.

## 🚀 Tech Stack
* **Backend:** FastAPI, Python
* **AI / Agentic Logic:** LangGraph, LangChain, OpenAI (gpt-4o-mini)
* **Frontend:** HTML5, CSS3 (Flexbox/Grid), Vanilla JavaScript (Streams API)
* **Database:** SQLite (Chinook Sample Database)

## 🛠️ Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/sql-agent.git
   cd sql-agent
   ```

2. **Set up the virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory and add your OpenAI API Key:
   ```env
   OPENAI_API_KEY=sk-your-api-key-here
   ```

5. **Run the Application:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   Open `http://localhost:8000` in your web browser to access the workspace!
