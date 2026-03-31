import os
from sentence_transformers import SentenceTransformer
from loguru import logger

class EmbeddingEngine:
    def __init__(self):
        model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.model = SentenceTransformer(model_name)
        logger.info(f"Loaded embedding model: {model_name}")
    
    def embed(self, text: str) -> list[float]:
        """Return 768-dim embedding vector."""
        return self.model.encode(text, convert_to_tensor=False).tolist()
import os
from sentence_transformers import SentenceTransformer
from loguru import logger

class EmbeddingEngine:
    def __init__(self):
        model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.model = SentenceTransformer(model_name)
        logger.info(f"Loaded embedding model: {model_name}")
    
    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, convert_to_tensor=False).tolist()