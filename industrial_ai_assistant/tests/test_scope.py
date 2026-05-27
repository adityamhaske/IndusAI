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
    
    import pytest
    from app.core.project_exceptions import ProjectNotReadyError
    
    print("Testing STRICT mode file explanation fast-path (expects ProjectNotReadyError)...")
    with pytest.raises(ProjectNotReadyError):
        res = orch.query(req)

if __name__ == "__main__":
    test_scope()
