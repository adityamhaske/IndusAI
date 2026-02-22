#!/bin/bash

# ==================================================
# IndusAI One-Click Start/Stop Script
# ==================================================

echo "🧹 Pre-cleaning lingering ports (8001, 5173, 6333, 11434) to ensure a clean boot..."
lsof -ti:8001,5173,6333,11434 | xargs kill -9 2>/dev/null || true

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

# Trap Ctrl+C (SIGINT), Kill (SIGTERM), and general exit to trigger cleanup
trap cleanup INT TERM EXIT

# 1. Qdrant
echo "➤ Starting Qdrant (Vector DB)..."
if [ -f "/tmp/qdrant" ]; then
    /tmp/qdrant > qdrant.log 2>&1 &
    PIDS+=($!)
else
    echo "   ⚠️ Binary at /tmp/qdrant not found. Assuming Qdrant is running globally or in Docker."
fi

# 2. Ollama
echo "➤ Starting Ollama (LLM Engine)..."
if command -v ollama &> /dev/null; then
    ollama serve > ollama.log 2>&1 &
    PIDS+=($!)
else
    echo "   ⚠️ Ollama binary not found in PATH."
fi

# 3. Backend
echo "➤ Starting FastAPI Backend..."
export PYTHONPATH="$(pwd)"
if [ -d "venv" ]; then
    source venv/bin/activate
fi
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload > backend.log 2>&1 &
PIDS+=($!)

# 4. Frontend
echo "➤ Starting React Vite Frontend..."
echo "   ⏳ Waiting 3 seconds for backend to initialize..."
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

# Wait indefinitely for background processes until interrupted
wait
