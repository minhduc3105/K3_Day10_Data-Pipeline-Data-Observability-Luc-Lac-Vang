from __future__ import annotations

from functools import lru_cache
import hashlib
import math

try:
    from langchain_core.embeddings import Embeddings
except ModuleNotFoundError:
    class Embeddings:
        pass

try:
    from sentence_transformers import SentenceTransformer
except ModuleNotFoundError:
    SentenceTransformer = None


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    if SentenceTransformer is None:
        return None
    return SentenceTransformer(model_name)


class MiniLMEmbeddings(Embeddings):
    def __init__(self, model_name: str):
        self.model = _load_model(model_name)
        self.backend = "sentence-transformers" if self.model is not None else "hashing-fallback"

    @staticmethod
    def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
        vector = [0.0] * dimensions
        tokens = text.lower().split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.model is None:
            return [self._hash_embedding(text) for text in texts]
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        if self.model is None:
            return self._hash_embedding(text)
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()
