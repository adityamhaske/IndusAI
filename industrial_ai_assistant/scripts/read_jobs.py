import os
import sys

# Set credentials and options before importing firebase
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/adityamhaske/Documents/projects/IndusAI/industrial_ai_assistant/indus-ai-cloud-101-firebase-adminsdk-fbsvc-006a5f3d3b.json"
os.environ["FIREBASE_STORAGE_BUCKET"] = "indus-ai-cloud-101.firebasestorage.app"

# Ensure app path is in sys.path
sys.path.insert(0, "/Users/adityamhaske/Documents/projects/IndusAI/industrial_ai_assistant")

from google.cloud import firestore

def main():
    print("Connecting to Firestore...")
    db = firestore.Client()
    
    print("\n--- Querying settings by Collection Group (profile) ---")
    settings_docs = db.collection_group("profile").stream()
    settings_list = list(settings_docs)
    print(f"Found {len(settings_list)} profile documents.")
    for doc in settings_list:
        path = doc.reference.path
        print(f"\nPath: {path}")
        for k, v in doc.to_dict().items():
            if "key" in k.lower() or "credential" in k.lower():
                print(f"    {k}: [MASKED]")
            else:
                print(f"    {k}: {v}")
                
    print("\n--- Querying ingest_jobs by Collection Group (no sorting) ---")
    jobs_docs = db.collection_group("ingest_jobs").stream()
    jobs_list = list(jobs_docs)
    print(f"Found {len(jobs_list)} ingest jobs.")
    for doc in jobs_list:
        path = doc.reference.path
        print(f"\nPath: {path}")
        for k, v in doc.to_dict().items():
            print(f"    {k}: {v}")

if __name__ == "__main__":
    main()
