import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

import numpy as np
from pinecone import ServerlessSpec
from pinecone_text.sparse import BM25Encoder, SpladeEncoder, SparseVector

from app.core.clients import async_openai_client, pinecone_client
from app.indexing.documents import Document

logger = logging.getLogger(__name__)

INDEX_NAME = "github-repo-index"


class BaseIndexer(ABC):
    """Abstract base for all indexers.

    Subclasses must set SUMMARIZE_PROMPT and implement:
      - _build_search_filter(query) -> dict
      - _reconstruct_document(fields) -> Document
    """

    SUMMARIZE_PROMPT: str  # set by each subclass

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        if not pinecone_client.has_index(INDEX_NAME):
            pinecone_client.create_index(
                name=INDEX_NAME,
                vector_type="dense",
                dimension=1536,
                metric="dotproduct",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self.index = pinecone_client.Index(INDEX_NAME)

    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------

    async def summarize_element(self, document: Document) -> str:
        messages = [
            {"role": "system", "content": self.SUMMARIZE_PROMPT},
            {"role": "user", "content": f"Document chunk:\n\n{document.model_dump_json(indent=2, exclude_none=True)}"},
        ]
        try:
            response = await async_openai_client.responses.create(
                model="gpt-4.1-nano",
                input=messages,
                temperature=0.1,
                timeout=30.0,
            )
            return response.output_text
        except Exception as e:
            logger.error(f"summarize_element failed: {e}")

    async def summarize_batch(self, documents: list[Document]) -> list[Document]:
        tasks = [asyncio.create_task(self.summarize_element(doc)) for doc in documents]
        descriptions = await asyncio.gather(*tasks, return_exceptions=True)
        for doc, desc in zip(documents, descriptions):
            if isinstance(desc, str):
                doc.description = desc.strip()
        return documents

    async def summarize_all(self, documents: list[Document], batch_size: int = 500) -> list[Document]:
        for i in range(0, len(documents), batch_size):
            await self.summarize_batch(documents[i:i + batch_size])
        return documents

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def embed_batch(self, batch: list[Document]) -> list[list[float]]:
        response = await async_openai_client.embeddings.create(
            input=[doc.description for doc in batch],
            model="text-embedding-3-small",
        )
        return [res.embedding for res in response.data]

    async def embed_all(self, documents: list[Document], batch_size: int = 1000) -> list[list[float]]:
        embeddings = []
        for i in range(0, len(documents), batch_size):
            embeddings.extend(await self.embed_batch(documents[i:i + batch_size]))
        return embeddings

    # ------------------------------------------------------------------
    # Sparse encoding
    # ------------------------------------------------------------------

    def bm25_encode(self, documents: list[Document]) -> list[SparseVector]:
        bm25 = BM25Encoder()
        corpus = [doc.text for doc in documents]
        bm25.fit(corpus)
        params_dir = Path(__file__).parent.parent.parent.parent / "BM25_params"
        params_dir.mkdir(exist_ok=True)
        bm25.dump(params_dir / f"{self.namespace}.json")
        return bm25.encode_documents(corpus)

    def splade_encode(
        self,
        documents: list[Document],
        max_characters: int = 1000,
        stride: int = 500,
        batch_size: int = 32,
    ) -> list[SparseVector]:
        encoder = SpladeEncoder()

        def _windows(text: str) -> list[str]:
            if not text:
                return []
            return [
                text[s:s + max_characters].strip()
                for s in range(0, len(text), stride)
                if text[s:s + max_characters].strip()
            ]

        windows: list[tuple[int, str]] = []
        for doc_id, doc in enumerate(documents):
            for w in _windows(doc.text) or ([doc.text] if doc.text.strip() else []):
                windows.append((doc_id, w))

        if not windows:
            return [{"indices": [], "values": []} for _ in documents]

        merged: list[dict[int, float]] = [defaultdict(float) for _ in documents]
        for i in range(0, len(windows), batch_size):
            batch_texts = [w for _, w in windows[i:i + batch_size]]
            vectors = encoder.encode_documents(batch_texts)
            for (doc_id, _), vec in zip(windows[i:i + batch_size], vectors):
                for idx, val in zip(vec["indices"], vec["values"]):
                    merged[doc_id][idx] = max(val, merged[doc_id].get(idx, 0.0))

        output: list[SparseVector] = []
        for m in merged:
            if not m:
                output.append({"indices": [], "values": []})
            else:
                indices, values = zip(*sorted(m.items()))
                output.append({"indices": list(indices), "values": list(values)})
        return output

    def encode_sparse_query(self, query: str, sparse_bm25: bool = True) -> SparseVector:
        if sparse_bm25:
            encoder = BM25Encoder()
            encoder.load(Path(__file__).parent.parent.parent.parent / "BM25_params" / f"{self.namespace}.json")
        else:
            encoder = SpladeEncoder()
        return encoder.encode_queries(query)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _is_index_empty(self) -> bool:
        stats = self.index.describe_index_stats()
        return stats.get("namespaces", {}).get(self.namespace, {}).get("vector_count", 0) == 0

    def _l2_normalize(self, vectors: list[list[float]], eps: float = 1e-12) -> list[list[float]]:
        arr = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return (arr / np.maximum(norms, eps)).tolist()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_data(
        self,
        documents: list[Document],
        sparse_bm25: bool = True,
        batch_size: int = 100,
        alpha: float = 0.8,
    ) -> None:
        if not self._is_index_empty():
            return

        documents = [doc for doc in documents if doc.text]
        documents = await self.summarize_all(documents)
        documents = [doc for doc in documents if doc.description]
        dense = self._l2_normalize(await self.embed_all(documents))
        sparse = self.bm25_encode(documents) if sparse_bm25 else self.splade_encode(documents)

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            metadata = [doc.model_dump(exclude_none=True) for doc in batch]
            data = [
                {
                    "id": str(uuid.uuid4()),
                    "values": (np.array(dense[i + j]) * alpha).tolist(),
                    "sparse_values": {
                        "indices": sparse[i + j]["indices"],
                        "values": (np.array(sparse[i + j]["values"]) * (1 - alpha)).tolist(),
                    },
                    "metadata": metadata[j],
                }
                for j, _ in enumerate(batch)
                if len(str(metadata[j])) < 35000
            ]
            try:
                self.index.upsert(vectors=data, namespace=self.namespace)
            except Exception as e:
                logger.error(f"Upsert failed: {e}")

    # ------------------------------------------------------------------
    # Search hooks (implemented by subclasses)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _build_search_filter(self, query: str) -> dict:
        """Return a Pinecone metadata filter dict for the given query."""
        ...

    @abstractmethod
    def _reconstruct_document(self, fields: dict) -> Document:
        """Reconstruct a Document from a Pinecone hit's fields dict."""
        ...

    # ------------------------------------------------------------------
    # Search (shared skeleton)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 15,
        with_filters: bool = True,
        with_rerank: bool = True,
        sparse_bm25: bool = True,
    ) -> list[Document]:
        filters = await self._build_search_filter(query) if with_filters else {}

        rerank = (
            {"model": "cohere-rerank-3.5", "query": query, "top_n": max_results, "rank_fields": ["description"]}
            if with_rerank
            else None
        )

        dense_embedding = (
            await async_openai_client.embeddings.create(input=query, model="text-embedding-3-small")
        ).data[0].embedding

        sparse_embedding = self.encode_sparse_query(query, sparse_bm25)
        if isinstance(sparse_embedding, dict):
            sparse_indices = sparse_embedding.get("indices", [])
            sparse_values = sparse_embedding.get("values", [])
        else:
            sparse_indices = getattr(sparse_embedding, "indices", [])
            sparse_values = getattr(sparse_embedding, "values", [])

        vector_payload: dict = {"values": dense_embedding}
        if sparse_indices:
            vector_payload.update({"sparse_values": sparse_values, "sparse_indices": sparse_indices})

        result = self.index.search(
            namespace=self.namespace,
            query={
                "vector": vector_payload,
                "top_k": max_results * 3 if with_rerank else max_results,
                "filter": filters,
            },
            rerank=rerank,
        )

        return [self._reconstruct_document(hit["fields"]) for hit in result["result"]["hits"]]
