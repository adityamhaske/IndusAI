#!/bin/bash

# ==================================================
# IndusAI One-Click Start/Stop Script (Phase 20+)
# Auto-setup for Mac/Linux environments
# ==================================================

# ── 1. Dependency Checks & Installations ──────────────────────────────────────
echo "🔍 Checking System Dependencies..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is required but not installed."
    exit 1
fi

# Check Node
if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm is required but not installed."
    exit 1
fi

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is required but not installed. Please install from https://ollama.com/"
    exit 1
fi

# Auto-download Qdrant if missing
if [ ! -f "./qdrant" ] && ! command -v qdrant &> /dev/null; then
    echo "📦 Qdrant binary not found. Downloading for Mac ARM64..."
    curl -L -o qdrant-aarch64-apple-darwin.tar.gz "https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-aarch64-apple-darwin.tar.gz"
    tar -xzf qdrant-aarch64-apple-darwin.tar.gz
    rm qdrant-aarch64-apple-darwin.tar.gz
    chmod +x qdrant
    echo "✅ Qdrant downloaded and extracted."
fi

# Setup Python venv and install requirements
echo "📦 Checking Python Dependencies..."
if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q
echo "✅ Python dependencies ready."

# Setup Frontend requirements
echo "📦 Checking Frontend Dependencies..."
cd client || exit
if [ ! -d "node_modules" ]; then
    echo "   Installing npm packages for frontend..."
    npm install
else
    # Just a quick check passing quietly
    npm install --prefer-offline --no-audit --loglevel ERROR
fi
cd ..
echo "✅ Frontend dependencies ready."

# ── 2. Pre-flight Cleanup ─────────────────────────────────────────────────────
echo "🧹 Pre-cleaning lingering ports (8001, 5173, 6333, 11434) to ensure a clean boot..."
lsof -ti:8001,5173,6333,11434 | xargs kill -9 2>/dev/null || true

# ── 3. Boot sequence ──────────────────────────────────────────────────────────
echo "🚀 Booting up IndusAI Platform..."
PIDS=()

cleanup() {
    echo ""
    echo "🛑 Break signal received. Shutting down all IndusAI services..."
    trap - INT TERM EXIT
    
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done
    
    echo "🧹 Ensuring all ports are freed..."
    lsof -ti:8001,5173,6333,11434 | xargs kill -9 2>/dev/null || true
    
    echo "✅ IndusAI safely closed. Goodbye!"
    exit 0
}

trap cleanup INT TERM EXIT

# Start Qdrant
echo "➤ Starting Qdrant (Vector DB)..."
if [ -f "./qdrant" ]; then
    ./qdrant > qdrant.log 2>&1 &
    PIDS+=($!)
elif command -v qdrant &> /dev/null; then
    qdrant > qdrant.log 2>&1 &
    PIDS+=($!)
fi

# Start Ollama
echo "➤ Starting Ollama (LLM Engine)..."
ollama serve > ollama.log 2>&1 &
PIDS+=($!)

# Wait a second for Ollama to spin up
sleep 1
# Pre-pull or verify model silently
echo "➤ Checking Ollama model: llama3.2"
ollama run llama3.2 "hello" > /dev/null 2>&1 &

# Start Backend
echo "➤ Starting FastAPI Backend..."
export PYTHONPATH="$(pwd)"
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload > backend.log 2>&1 &
PIDS+=($!)

# Start Frontend
echo "➤ Starting React Vite Frontend..."
echo "   ⏳ Waiting 3 seconds for backend DB init..."
sleep 3
cd client || exit
npm run dev > ../frontend.log 2>&1 &
PIDS+=($!)
cd ..

echo "======================================================"
echo "🎉 IndusAI is LIVE!"
echo "   🌐 UI:       http://localhost:5173"
echo "   🧠 Backend:  http://localhost:8001"
echo "------------------------------------------------------"
echo "⚠️  KEEP THIS TERMINAL OPEN."
echo "   Press [Ctrl+C] to safely close EVERYTHING in 1 step."
echo "======================================================"

wait
