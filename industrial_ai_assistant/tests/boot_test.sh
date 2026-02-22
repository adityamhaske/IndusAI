#!/bin/bash
export PYTHONPATH="/Users/adityamhaske/Documents/projects/PLC Fault/prot1.1/prot 2/industrial_ai_assistant"
cd "$PYTHONPATH"

# Kill anything on 8000 just in case
lsof -t -i:8000 | xargs kill -9 2>/dev/null

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

echo "Waiting for uvicorn to start..."
for i in {1..30}; do
  if curl -s http://localhost:8000/api/system/health > /dev/null; then
    echo "Server is up!"
    break
  fi
  sleep 1
done

echo "--- /api/system/version ---"
curl -s http://localhost:8000/api/system/version
echo -e "\n"

echo "--- /api/system/health ---"
curl -s http://localhost:8000/api/system/health
echo -e "\n"

echo "--- /api/ai/health ---"
curl -s http://localhost:8000/api/ai/health
echo -e "\n"

echo "--- /api/ai/metrics ---"
curl -s http://localhost:8000/api/ai/metrics
echo -e "\n"

kill $SERVER_PID
wait $SERVER_PID 2>/dev/null
echo "Server terminated cleanly."
