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
    DB_PATH: str = "./data/app.db"

    # Components
    LLM_PROVIDER: Literal["ollama", "mock"] = "ollama"
    EMBEDDING_PROVIDER: Literal["sentence_transformers", "mock"] = "sentence_transformers"
    VECTOR_STORE_TYPE: Literal["qdrant", "in_memory"] = "qdrant"
    RETRIEVER_TYPE: Literal["hybrid", "keyword"] = "hybrid"

    # Component Configs
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "industrial_docs"
    
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
