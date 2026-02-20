import json
import time
from app.api.routes_knowledge import KnowledgeQueryRequest
from app.services.query_orchestrator import get_query_orchestrator
from app.models.project_models import ProjectQueryRequest

def test_scope():
    orch = get_query_orchestrator()
    
    req = ProjectQueryRequest(
        question="Explain ISO_IO_List.txt",
        project_id="default",
        top_k=5,
        selected_files=["ISO_IO_List.txt"],
        selected_folders=[],
        scope_mode="STRICT"
    )
    
    print("Testing STRICT mode file explanation fast-path...")
    res = orch.query(req)
    
    print("\n--- RESULTS ---")
    print("Truncated:", res.context_scope.get("truncated"))
    print("Total Candidates:", res.context_scope.get("total_candidates"))
    print("Used Chunks:", res.context_scope.get("used_chunks"))
    print("Answer:")
    try:
        print(json.loads(res.answer)["summary"])
    except:
        print(res.answer)

if __name__ == "__main__":
    test_scope()
