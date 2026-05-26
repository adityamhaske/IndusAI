import os
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Paths
    DATA_DIR: str = "./data"
    DB_PATH: str = os.environ.get("DB_PATH", "/tmp/app.db")

    # Components
    LLM_PROVIDER: Literal["gemini", "ollama", "mock"] = "gemini"
    EMBEDDING_PROVIDER: Literal["gemini", "sentence_transformers", "mock"] = "gemini"
    VECTOR_STORE_TYPE: Literal["cloud", "qdrant", "in_memory"] = "cloud"
    RETRIEVER_TYPE: Literal["hybrid", "keyword"] = "hybrid"

    # Component Configs
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "industrial_docs"
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    
    FIREBASE_STORAGE_BUCKET: str = ""

    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # API Keys (Injected via Environment, never logged)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Deployment Feature Flags (Canary / Cost Guards)
    ENABLE_CLOUD_PROVIDERS: bool = False
    ENABLE_SPECULATIVE_FALLBACK: bool = False
    MAX_DAILY_COST_USD: float = 5.0
    
    GOLDEN_DATASET_PATH: str = "./golden_dataset.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
