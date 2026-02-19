<div align="center">
  <h1>🏭 IndusAI — Industrial AI Assistant</h1>
  <p><strong>v1.0</strong> · PLC Fault Analysis with RAG + Local LLM</p>

  ![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
  ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)
  ![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)
  ![Ollama](https://img.shields.io/badge/LLM-Ollama%20mistral-ff6b35)
  ![Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-dc244c)
  ![License](https://img.shields.io/badge/License-MIT-green)
</div>

---

## 🎯 What It Does

IndusAI is a privacy-first industrial AI assistant that runs 100% locally. It analyzes PLC (Programmable Logic Controller) fault logs using:

- **Deterministic statistics** — occurrence frequency, burst detection, co-occurrence analysis
- **RAG (Retrieval-Augmented Generation)** — retrieves relevant sections from indexed industrial documentation
- **Local LLM reasoning** — Ollama + Mistral 7B generates structured fault explanations (no cloud APIs)
- **Strict output validation** — hallucinated PLC tags are detected and stripped before the response reaches the user

## ✨ Features

| Feature | Details |
|---|---|
| 📂 CSV Upload | Drop any PLC fault log — 20+ column aliases auto-mapped |
| 🔍 RAG Retrieval | Hybrid vector + keyword search across indexed documentation |
| 🤖 Local LLM | Mistral 7B via Ollama — fully offline, no OpenAI |
| 📊 Deterministic Stats | Occurrences, burst detection, co-faults — never recomputed by LLM |
| ❓ Custom Q&A | Ask a specific question about any fault row |
| 🏥 System Health | Real-time header badge — LLM, RAG, Vector DB status |
| 🚫 No Silent Fallback | Explicit error if LLM/RAG unreachable — no misleading mock responses |

## 🏗️ Architecture

```
CSV Upload ──→ Schema Normalizer ──→ FaultService (in-memory)
                                          │
User clicks "Ask AI" ──────────────→ FaultAnalysisOrchestrator
                                          ├── SystemHealthService  (pre-flight check)
                                          ├── FaultService         (deterministic stats)
                                          ├── RAGService           (HybridRetriever → Qdrant)
                                          ├── OllamaLLM            (Mistral 7B, local)
                                          └── FaultResponseValidator (hallucination check)
                                                    │
                                            FaultAnalysisV2Response ──→ React UI
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) — `brew install ollama`
- [Qdrant](https://qdrant.tech) binary (see below)

### 1. Backend

```bash
cd industrial_ai_assistant

# Create virtualenv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Create data dir
mkdir -p data

# Start Qdrant (download binary)
curl -fsSL "https://github.com/qdrant/qdrant/releases/download/v1.11.5/qdrant-aarch64-apple-darwin.tar.gz" \
  -o /tmp/qdrant.tar.gz && tar -xzf /tmp/qdrant.tar.gz -C /tmp
/tmp/qdrant &

# Start Ollama + pull model
ollama serve &
ollama pull mistral

# Start backend
PYTHONPATH=. ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend

```bash
cd industrial_ai_assistant/client
npm install
npm run dev
# → http://localhost:5173
```

### 3. Verify everything is healthy

```bash
curl http://localhost:8001/api/system/health
# {"status":"healthy","llm_connected":true,"rag_connected":true,"vector_store_connected":true}
```

## 📡 API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/fault/upload` | Upload PLC fault CSV |
| GET | `/api/fault/list` | Paginated fault rows |
| GET | `/api/fault/summary` | Aggregate statistics |
| GET | `/api/fault/detail` | Single row + history |
| POST | `/api/fault/analyze` | LLM analysis (+ optional question) |
| GET | `/api/system/health` | System connectivity status |
| POST | `/api/chat` | RAG-based doc Q&A |

## 🧪 Tests

```bash
cd industrial_ai_assistant
PYTHONPATH=. ./venv/bin/pytest tests/ -v
# 47 tests — schema normalization, upload, summary, analysis, RAG integration
```

## 📁 Project Structure

```
industrial_ai_assistant/
├── app/
│   ├── api/             # FastAPI routes
│   ├── core/            # Interfaces, exceptions, schemas
│   ├── config/          # DI container, settings
│   ├── embeddings/      # SentenceTransformer + mock
│   ├── llm/             # Ollama + mock LLM
│   ├── models/          # Pydantic v2 models
│   ├── retrieval/       # HybridRetriever, keyword search
│   ├── services/        # Orchestrators, health, RAG, validation
│   ├── utils/           # Schema normalizer, stats, confidence
│   └── vector_store/    # Qdrant + in-memory store
├── client/              # React 18 + Tailwind frontend
│   └── src/
│       ├── api/         # faultApi.js, systemApi.js
│       ├── components/  # Header, Dashboard panels
│       └── pages/       # LogsPage, ChatPage
├── tests/               # pytest test suite (47 tests)
└── docs/                # Evaluation checklist, risk analysis
```

## ⚙️ Configuration

Copy `.env.example` to `.env` and adjust:

```env
LLM_PROVIDER=ollama          # or mock
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
VECTOR_STORE_TYPE=qdrant     # or in_memory
QDRANT_HOST=localhost
QDRANT_PORT=6333
EMBEDDING_PROVIDER=sentence_transformers
DEBUG_LLM=false              # Set true to log full LLM prompts
```

## 🔒 Privacy

All processing is 100% local:
- LLM runs via Ollama on your machine
- Documents indexed in local Qdrant instance
- No data leaves your network

## 📄 License

MIT — see [LICENSE](LICENSE)

---

<div align="center">
  Built with ❤️ for industrial engineers who need reliable, explainable AI — not black boxes.
</div>
