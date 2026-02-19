from functools import lru_cache
from app.config.settings import settings

# Interfaces
from app.core.interfaces.llm_interface import LLMInterface
from app.core.interfaces.embedding_interface import EmbeddingInterface
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.interfaces.retriever_interface import RetrieverInterface
from app.core.interfaces.chunker_interface import ChunkerInterface

# Implementations
from app.llm.ollama_llm import OllamaLLM
from app.llm.mock_llm import MockLLM
from app.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from app.embeddings.mock_embedder import MockEmbedder
from app.vector_store.qdrant_store import QdrantStore
from app.vector_store.in_memory_store import InMemoryStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import Reranker
from app.chunking.semantic_chunker import SemanticChunker
from app.chunking.fixed_token_chunker import FixedTokenChunker
from app.ingestion.ingestion_manager import IngestionManager
from app.ingestion.processors import PDFProcessor, L5XProcessor, ExcelProcessor
from app.storage.sqlite_client import SQLiteClient

from app.services.chat_service import ChatService
from app.services.validation_service import ValidationService
from app.services.history_service import HistoryService
from app.services.log_service import LogService
from app.services.project_service import ProjectService
from app.services.evaluation_service import EvaluationService
from app.services.rag_service import RAGService
from app.services.fault_response_validator import FaultResponseValidator
from app.services.fault_analysis_orchestrator import FaultAnalysisOrchestrator

class Container:
    def __init__(self):
        self._db_client = SQLiteClient(db_path=settings.DB_PATH)
        
        # 1. Embeddings
        if settings.EMBEDDING_PROVIDER == "sentence_transformers":
            self._embedder = SentenceTransformerEmbedder(model_name=settings.EMBEDDING_MODEL_NAME)
        else:
            self._embedder = MockEmbedder()
            
        # 2. Vector Store
        if settings.VECTOR_STORE_TYPE == "qdrant":
            self._vector_store = QdrantStore(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                collection_name=settings.QDRANT_COLLECTION
            )
        else:
            self._vector_store = InMemoryStore()
            
        # 3. LLM
        if settings.LLM_PROVIDER == "ollama":
            self._llm = OllamaLLM(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)
        else:
            self._llm = MockLLM()
            
        # 4. Retrieval
        self._keyword_retriever = KeywordSearch()
        self._reranker = Reranker()
        
        if settings.RETRIEVER_TYPE == "hybrid":
            self._retriever = HybridRetriever(
                vector_store=self._vector_store,
                embedder=self._embedder,
                keyword_retriever=self._keyword_retriever,
                reranker=self._reranker
            )
        else:
            # Fallback or other types could be handled here
            self._retriever = HybridRetriever(
                vector_store=self._vector_store,
                embedder=self._embedder,
                keyword_retriever=self._keyword_retriever
            )
            
        # 5. Services
        self._validator = ValidationService()
        self._chat_service = ChatService(
            llm=self._llm,
            retriever=self._retriever,
            validator=self._validator,
            db_client=self._db_client
        )
        self._history_service = HistoryService(db_client=self._db_client)
        self._log_service = LogService(db_client=self._db_client)
        self._project_service = ProjectService(db_client=self._db_client)
        self._evaluation_service = EvaluationService(
            chat_service=self._chat_service,
            golden_dataset_path=settings.GOLDEN_DATASET_PATH
        )
        
        # 6. Ingestion
        self._chunker = SemanticChunker() # Default to semantic
        self._processors = {
            "pdf": PDFProcessor(self._chunker),
            "l5x": L5XProcessor(self._chunker),
            "xlsx": ExcelProcessor(self._chunker)
        }
        self._ingestion_manager = IngestionManager(
            vector_store=self._vector_store,
            embedder=self._embedder,
            processors=self._processors
        )

        # 7. Fault Analysis Orchestration
        self._rag_service = RAGService(retriever=self._retriever)
        self._fault_response_validator = FaultResponseValidator()
        self._fault_orchestrator = FaultAnalysisOrchestrator(
            llm=self._llm,
            rag_service=self._rag_service,
            validator=self._fault_response_validator,
        )

    # Accessors
    @property
    def chat_service(self) -> ChatService:
        return self._chat_service
        
    @property
    def history_service(self) -> HistoryService:
        return self._history_service
        
    @property
    def log_service(self) -> LogService:
        return self._log_service
        
    @property
    def project_service(self) -> ProjectService:
        return self._project_service
        
    @property
    def evaluation_service(self) -> EvaluationService:
        return self._evaluation_service
        
    @property
    def ingestion_manager(self) -> IngestionManager:
        return self._ingestion_manager

    @property
    def fault_orchestrator(self) -> FaultAnalysisOrchestrator:
        return self._fault_orchestrator

    @property
    def rag_service(self) -> RAGService:
        return self._rag_service

# Singleton instance
@lru_cache()
def get_container() -> Container:
    return Container()
