from __future__ import annotations

"""Vector store abstraction supporting Amazon OpenSearch Serverless and local OpenSearch."""

import math
import threading
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection, helpers
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import OpenSearchException, TransportError
from tqdm.auto import tqdm

from src.utils.config import get_settings
from src.utils.logger import get_logger, log_error


class VectorStoreError(RuntimeError):
    """Raised when vector store operations fail."""


INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "text": {"type": "text"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 768,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                },
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "source": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "size_min_mm": {"type": "float"},
                    "size_max_mm": {"type": "float"},
                    "risk_level": {"type": "keyword"},
                },
            },
        }
    }
}


class VectorStore:
    """High-level interface for similarity and hybrid search over guideline documents."""

    REQUEST_TIMEOUT = 30
    RETRY_ATTEMPTS = 3

    def __init__(self, index_name: str = "medical_guidelines") -> None:
        self._logger = get_logger("audra.services.vector_store")
        self._settings = get_settings()
        self.index_name = index_name
        self._client = self._create_client()
        self._lock = threading.Lock()
        self._ensure_index()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def index_document(
        self,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, object],
    ) -> None:
        """Index (or upsert) a single document."""

        document = {"text": text, "embedding": embedding, "metadata": metadata}
        self._execute_with_retry(
            lambda: self._client.index(
                index=self.index_name,
                id=doc_id,
                document=document,
                refresh="wait_for",
                request_timeout=self.REQUEST_TIMEOUT,
            ),
            operation="index_document",
            context={"doc_id": doc_id},
        )

    def index_batch(self, documents: List[Dict[str, object]], batch_size: int = 100) -> None:
        """Bulk index a collection of documents."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if not documents:
            return

        total_batches = math.ceil(len(documents) / batch_size)
        iterator = range(0, len(documents), batch_size)

        for start in tqdm(
            iterator,
            total=total_batches,
            desc="Indexing documents",
            disable=total_batches <= 1,
        ):
            batch = documents[start : start + batch_size]
            actions = [
                {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": doc["id"],
                    "_source": {
                        "text": doc["text"],
                        "embedding": doc["embedding"],
                        "metadata": doc.get("metadata", {}),
                    },
                }
                for doc in batch
            ]
            self._execute_with_retry(
                lambda: helpers.bulk(
                    self._client,
                    actions,
                    refresh="wait_for",
                    request_timeout=self.REQUEST_TIMEOUT,
                ),
                operation="index_batch",
                context={"batch_start": start, "batch_count": len(batch)},
            )

    def search(
        self,
        query_embedding: List[float],
        *,
        top_k: int = 5,
        filters: Optional[Dict[str, object]] = None,
    ) -> List[Dict[str, object]]:
        """Perform kNN search with optional metadata filters."""

        body = self._build_knn_query(query_embedding, top_k=top_k, filters=filters)
        response = self._execute_with_retry(
            lambda: self._client.search(
                index=self.index_name,
                body=body,
                request_timeout=self.REQUEST_TIMEOUT,
            ),
            operation="search",
        )
        return self._format_hits(response)

    def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        *,
        top_k: int = 5,
    ) -> List[Dict[str, object]]:
        """Combine semantic kNN and BM25 keyword search via reciprocal rank fusion."""

        semantic_results = self._semantic_search(query_embedding, top_k=top_k * 3)
        keyword_results = self._keyword_search(query_text, top_k=top_k * 3)

        weight_semantic = 0.7
        weight_keyword = 0.3
        rrf_k = 60.0

        fused: Dict[str, Dict[str, object]] = {}
        for rank, hit in enumerate(semantic_results, start=1):
            doc_id = hit["id"]
            score = weight_semantic * (1.0 / (rrf_k + rank))
            fused.setdefault(doc_id, hit.copy())
            fused[doc_id]["score"] = fused.get(doc_id, {}).get("score", 0.0) + score

        for rank, hit in enumerate(keyword_results, start=1):
            doc_id = hit["id"]
            score = weight_keyword * (1.0 / (rrf_k + rank))
            fused.setdefault(doc_id, hit.copy())
            fused[doc_id]["score"] = fused.get(doc_id, {}).get("score", 0.0) + score

        sorted_hits = sorted(fused.values(), key=lambda item: item.get("score", 0.0), reverse=True)
        return sorted_hits[:top_k]

    def delete_index(self) -> None:
        """Delete the backing index. Intended for tests and cleanup."""

        self._execute_with_retry(
            lambda: self._client.indices.delete(index=self.index_name, ignore=[404]),
            operation="delete_index",
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _create_client(self) -> OpenSearch:
        endpoint = (
            str(self._settings.OPENSEARCH_ENDPOINT)
            if self._settings.OPENSEARCH_ENDPOINT
            else "http://localhost:9200"
        )
        parsed = urlparse(endpoint)

        is_local = parsed.hostname in {None, "localhost", "127.0.0.1"}
        if is_local:
            self._logger.debug(
                "Initializing local OpenSearch client.",
                extra={"context": {"endpoint": endpoint}},
            )
            return OpenSearch(
                hosts=[{"host": parsed.hostname or "localhost", "port": parsed.port or 9200}],
                http_compress=True,
                use_ssl=parsed.scheme == "https",
                verify_certs=False,
                connection_class=RequestsHttpConnection,
                timeout=self.REQUEST_TIMEOUT,
                max_retries=2,
                retry_on_timeout=True,
            )

        region = self._settings.AWS_REGION
        if not region:
            raise VectorStoreError("AWS_REGION must be configured for remote OpenSearch access.")

        self._logger.debug(
            "Initializing Amazon OpenSearch Serverless client.",
            extra={"context": {"endpoint": endpoint, "region": region}},
        )
        try:
            session = boto3.Session(region_name=region)
            credentials = session.get_credentials()
            if credentials is None:
                raise VectorStoreError("No AWS credentials available for OpenSearch.")
            auth = AWSV4SignerAuth(credentials, region, service="aoss")
        except (BotoCoreError, NoCredentialsError) as exc:
            log_error(exc, context={"operation": "create_client"})
            raise VectorStoreError("Failed to initialize AWS credentials for OpenSearch.") from exc

        return OpenSearch(
            hosts=[{"host": parsed.hostname, "port": parsed.port or 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=self.REQUEST_TIMEOUT,
            max_retries=3,
            retry_on_timeout=True,
        )

    def _ensure_index(self) -> None:
        with self._lock:
            exists = self._execute_with_retry(
                lambda: self._client.indices.exists(index=self.index_name),
                operation="check_index",
            )
            if exists:
                return
            self._logger.debug(
                "Creating vector index if absent.",
                extra={"context": {"index": self.index_name}},
            )
            self._execute_with_retry(
                lambda: self._client.indices.create(
                    index=self.index_name,
                    body=INDEX_MAPPING,
                ),
                operation="create_index",
            )

    def _execute_with_retry(
        self,
        func,
        *,
        operation: str,
        context: Optional[Dict[str, object]] = None,
    ):
        last_error: Optional[Exception] = None
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            try:
                return func()
            except (OpenSearchException, TransportError, OpenSearchConnectionError) as exc:
                last_error = exc
                self._logger.warning(
                    "Vector store operation failed; retrying.",
                    extra={
                        "context": {
                            "operation": operation,
                            "attempt": attempt,
                            "error": str(exc),
                        }
                    },
                )
                time.sleep(min(2 ** attempt, 8))
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
                break

        if last_error:
            detail = {"operation": operation}
            if context:
                detail.update(context)
            log_error(last_error, context=detail)
            raise VectorStoreError(f"Vector store operation '{operation}' failed.") from last_error
        return None

    def _build_knn_query(
        self,
        embedding: List[float],
        *,
        top_k: int,
        filters: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        num_candidates = max(top_k * 4, 50)
        knn_query: Dict[str, object] = {
            "field": "embedding",
            "query_vector": embedding,
            "k": top_k,
            "num_candidates": num_candidates,
        }

        filter_clause = self._build_filter_clause(filters)
        if filter_clause:
            knn_query["filter"] = filter_clause

        return {"knn": knn_query}

    def _build_filter_clause(self, filters: Optional[Dict[str, object]]) -> Optional[Dict[str, object]]:
        if not filters:
            return None

        clauses: List[Dict[str, object]] = []
        finding_size = filters.get("finding_size")
        if isinstance(finding_size, (int, float)):
            clauses.append({"range": {"metadata.size_min_mm": {"lte": finding_size}}})
            clauses.append({"range": {"metadata.size_max_mm": {"gte": finding_size}}})

        patient_risk = filters.get("patient_risk")
        if isinstance(patient_risk, str):
            clauses.append({"term": {"metadata.risk_level": patient_risk}})

        if not clauses:
            return None

        return {"bool": {"filter": clauses}}

    def _semantic_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, object]]:
        response = self._execute_with_retry(
            lambda: self._client.search(
                index=self.index_name,
                body=self._build_knn_query(query_embedding, top_k=top_k),
                request_timeout=self.REQUEST_TIMEOUT,
            ),
            operation="semantic_search",
        )
        return self._format_hits(response)

    def _keyword_search(self, query_text: str, top_k: int) -> List[Dict[str, object]]:
        body = {
            "size": top_k,
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["text^2", "metadata.category", "metadata.source"],
                }
            },
        }
        response = self._execute_with_retry(
            lambda: self._client.search(
                index=self.index_name,
                body=body,
                request_timeout=self.REQUEST_TIMEOUT,
            ),
            operation="keyword_search",
        )
        return self._format_hits(response)

    def _format_hits(self, response) -> List[Dict[str, object]]:
        hits = response.get("hits", {}).get("hits", [])
        formatted = []
        for hit in hits:
            formatted.append(
                {
                    "id": hit.get("_id"),
                    "text": hit.get("_source", {}).get("text"),
                    "metadata": hit.get("_source", {}).get("metadata", {}),
                    "score": hit.get("_score"),
                }
            )
        return formatted
