from pathlib import Path

# Project Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

# LLM Defaults
DEFAULT_LLM_MODEL = "mistral"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Retrieval Defaults
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.7

# Vector Store
COLLECTION_NAME = "industrial_docs"
VECTOR_SIZE = 384  # Depends on the embedding model
