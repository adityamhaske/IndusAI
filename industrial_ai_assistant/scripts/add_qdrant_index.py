import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.models import PayloadSchemaType

def main():
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    
    if not qdrant_url or not qdrant_api_key:
        print("Missing QDRANT_URL or QDRANT_API_KEY")
        sys.exit(1)

    print(f"Connecting to Qdrant at {qdrant_url}...")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    collection_name = "project_knowledge"

    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="project_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        print("Successfully created payload index on 'project_id'!")
    except Exception as e:
        print(f"Failed to create payload index: {e}")

if __name__ == "__main__":
    main()
