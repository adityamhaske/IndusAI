import os
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Config
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Paths (local data dir, used for temp uploads before Firebase Storage)
    DATA_DIR: str = "./data"

    # Retrieval
    RETRIEVER_TYPE: Literal["hybrid", "keyword"] = "hybrid"

    # Qdrant Cloud
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""

    # Firebase
    FIREBASE_STORAGE_BUCKET: str = ""

    # BYOK encryption key — used to AES-256 encrypt user API keys at rest in Firestore
    ENCRYPTION_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
