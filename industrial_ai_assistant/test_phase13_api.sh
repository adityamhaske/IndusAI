#!/bin/bash

# Audit HTTP runner to hit the live backend

QUERIES=(
    "explain me all these documents"
    "what is the main purpose of this project?"
    "give me a summary of the routine MainProgram"
    "how does the MOTOR_SPEED tag work?"
    "explain the fault code F001"
    "what are the key fields in the file structure?"
    "describe the IO configuration"
    "what is the role of the safety relay?"
    "how to reset the system after emergency stop"
    "can you list all the alarms in the system?"
)

echo "Starting Phase 13 Audit queries against localhost:8001"

for i in "${!QUERIES[@]}"; do
    query="${QUERIES[$i]}"
    echo ""; sleep 2
    echo "============================================"
    echo "Query $((i+1)): $query"
    echo "============================================"
    
    curl -s -X POST http://localhost:8001/api/knowledge/query \
      -H "Content-Type: application/json" \
      -d '{
        "question": "'"$query"'",
        "project_id": "default",
        "top_k": 5
      }' | grep -o '"summary":.*' | head -c 200
      
    echo "..."
done
echo ""; sleep 2
echo "Done hitting queries."
