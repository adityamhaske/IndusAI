import asyncio
import json
import os
import sys

# Setup environment to run locally
sys.path.insert(0, os.path.abspath("."))

from app.services.query_orchestrator import get_query_orchestrator
from app.models.project_models import ProjectQueryRequest
from app.config.dependency_injection import get_container

# We need to initialize the container to mock the context
container = get_container()

# List of test queries
QUERIES = [
    "explain me all these documents",
    "what is the main purpose of this project?",
    "give me a summary of the routine MainProgram",
    "how does the MOTOR_SPEED tag work?",
    "explain the fault code F001",
    "what are the key fields in the file structure?",
    "describe the IO configuration",
    "what is the role of the safety relay?",
    "how to reset the system after emergency stop",
    "can you list all the alarms in the system?"
]

def run_tests():
    orchestrator = get_query_orchestrator()
    
    logs = []
    
    for i, query in enumerate(QUERIES):
        print(f"Running query {i+1}/{len(QUERIES)}: {query}")
        
        req = ProjectQueryRequest(
            question=query,
            project_id="default",
            top_k=5,
        )
        
        try:
            res = orchestrator.query(req)
            
            # Extract raw output, etc. This is tricky because raw_output isn't directly exposed in ProjectQueryResponse.
            # I will need to temporarily monkey-patch or instrument QueryOrchestrator to get this.
            
            print(f"Success. Answer len: {len(res.answer)}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    run_tests()
