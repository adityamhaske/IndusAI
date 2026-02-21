# Running and Closing IndusAI End-to-End

This guide provides the complete, end-to-end steps to run the IndusAI assistant locally, as well as how to completely shut down all associated services (Backend, Frontend, Vector Database, and LLM).

---

## 🚀 1. Running the Project End-to-End

To get the entire stack up and running, you need to start four separate components: Qdrant (Vector DB), Ollama (LLM), the FastAPI Backend, and the React Frontend.

### Step 1: Start Qdrant (Vector DB)
IndusAI requires Qdrant to be running to serve as the semantic retrieval engine.
Open a new terminal and run:
```bash
# Path might vary based on where you downloaded Qdrant
# Usually it's in /tmp/qdrant if following the original README
/tmp/qdrant
```
*(Leave this terminal window open)*

### Step 2: Start Ollama (LLM Engine)
Ollama serves the Mistral model locally for text generation.
Open a second terminal and run:
```bash
ollama serve
```
*(Leave this terminal window open)*

### Step 3: Start the FastAPI Backend
The backend handles the core orchestration, retrieval, and API endpoints.
Open a third terminal, navigate to the `industrial_ai_assistant` folder, and activate the virtual environment:
```bash
cd "/Users/adityamhaske/Documents/projects/PLC Fault/prot1.1/prot 2/industrial_ai_assistant"
source venv/bin/activate

# Start the server on port 8001
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
*(Leave this terminal window open)*

### Step 4: Start the React Frontend
The frontend provides the Chat UI, File Explorer, and Scope controls.
Open a fourth terminal, navigate to the `client` folder:
```bash
cd "/Users/adityamhaske/Documents/projects/PLC Fault/prot1.1/prot 2/industrial_ai_assistant/client"

# Start the Vite development server
npm run dev
```

---

## 🎯 2. Using the Application

1. Open your browser to http://localhost:5173 
2. Go to **Settings** and upload/index a PLC project folder if you haven't already.
3. Go back to the **Chat** page, verify the "Project Knowledge Active" badge is green.
4. Select files from the right-hand **Project Explorer** to constrain the context scope.
5. Ask your questions!

---

## 🛑 3. Closing the Entire Project (Including All Backends)

When you are done, you MUST shut down all services to free up system memory and ports. 

### Method A: Manual Shutdown
Go to each of the four terminal windows you opened in Section 1 and press `Ctrl + C` to stop the running process.

### Method B: Kill-All Command
If you ran the processes in the background or lost the terminal windows, you can forcefully close everything by opening a single new terminal and running the following commands:

```bash
# 1. Kill the FastAPI Backend (Port 8001)
lsof -ti:8001 | xargs kill -9

# 2. Kill the Vite Frontend (Port 5173)
lsof -ti:5173 | xargs kill -9

# 3. Kill Qdrant (Port 6333)
lsof -ti:6333 | xargs kill -9

# 4. Kill Ollama (Port 11434)
# Note: On macOS, Ollama might also be running as a native menu bar app. 
# You may need to click the Ollama icon in the top right menu bar and select "Quit Ollama".
lsof -ti:11434 | xargs kill -9
```

Run this combined one-liner to kill the standard ports instantly:
```bash
lsof -ti:8001,5173,6333,11434 | xargs kill -9
```

This ensures the **Frontend**, **Python Backend**, **Vector Database**, and **LLM Engine** are completely terminated and your system resources are freed.
