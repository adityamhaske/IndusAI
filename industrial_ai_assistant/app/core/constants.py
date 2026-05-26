from pathlib import Path

# Project Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

# Retrieval Defaults
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.7
