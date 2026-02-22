import os
from app.config.settings import settings
from app.config.dependency_injection import get_container

def reset_all():
    print("--- Phase 11: Cold Start Wipe ---")
    # 1. Reset DB
    db_path = settings.DB_PATH
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Deleted SQLite DB at {db_path}")
    else:
        print(f"SQLite DB at {db_path} did not exist.")
    
    # 2. Reset Qdrant
    try:
        container = get_container()
        if hasattr(container._vector_store, 'delete_collection'):
            container._vector_store.delete_collection()
            print(f"Deleted Qdrant collection: {settings.QDRANT_COLLECTION}")
        else:
            print("Vector store does not support delete_collection.")
    except Exception as e:
        print(f"Error resetting Qdrant: {e}")

if __name__ == "__main__":
    reset_all()
