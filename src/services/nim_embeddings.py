from __future__ import annotations

"""Client for the NVIDIA Retrieval Embedding NIM (NV-Embed-v2)."""

import math
import threading
import time
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm.auto import tqdm

from src.utils.config import get_settings
from src.utils.logger import get_logger, log_error, log_nim_call
from src.services.nim_llm import NIMServiceError


class EmbeddingClient:
    """Client for retrieving embeddings from NVIDIA's NV-Embed-v2 NIM."""

    MODEL_NAME = "nvidia/nv-embed-v2"
    REQUEST_TIMEOUT_SECONDS = 30.0
    MAX_TOKENS = 512
    EMBEDDING_DIMENSION = 768

    def __init__(self) -> None:
        settings = get_settings()
        api_key = (
            settings.NIM_EMBEDDING_API_KEY.get_secret_value()
            if settings.NIM_EMBEDDING_API_KEY is not None
            else None
        )
        if not api_key:
            raise NIMServiceError("NIM embedding API key is not configured.")

        self._client = OpenAI(
            base_url=str(settings.NIM_EMBEDDING_ENDPOINT),
            api_key=api_key,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
        )
        self._logger = get_logger("audra.services.nim_embeddings")

        self._metrics_lock = threading.Lock()
        self._total_embeddings = 0
        self._latencies_ms: list[float] = []
        self._cache_hits = 0
        self._cache_lookups = 0

        self._retryer = Retrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception_type(
                (RateLimitError, APITimeoutError, APIConnectionError, APIError)
            ),
            reraise=True,
        )

        self._cached_fetch = lru_cache(maxsize=1024)(self._fetch_embedding_uncached)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def embed_text(self, text: str, prefix: Optional[str] = None) -> List[float]:
        """Generate a 768-dimensional embedding for the provided text."""

        if not text:
            raise ValueError("Text must be a non-empty string.")

        segments = self._segment_text(text)
        if prefix:
            segments = [f"{prefix}{segment}" for segment in segments]

        start_time = time.perf_counter()
        vectors: list[List[float]] = []
        cache_hits = 0
        token_count = 0
        for segment in segments:
            vector, cache_hit = self._fetch_with_cache(segment)
            vectors.append(vector)
            self._record_cache(cache_hit)
            if cache_hit:
                cache_hits += 1
            else:
                token_count += len(segment.split())

        combined = self._average_vectors(vectors)
        normalized = self._normalize(combined)

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        self._record_metrics(latency_ms)
        self._logger.debug(
            "Embedding request completed.",
            extra={
                "context": {
                    "operation": "embed_text",
                    "latency_ms": latency_ms,
                    "segments": len(segments),
                    "cache_hits": cache_hits,
                    "cache_misses": len(segments) - cache_hits,
                }
            },
        )
        cache_misses = len(segments) - cache_hits
        if cache_misses:
            log_nim_call(
                service="nv-embed",
                prompt_tokens=token_count,
                completion_tokens=0,
                latency_ms=latency_ms,
            )
        return normalized

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Embed a list of texts, processing them in batches."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        if not texts:
            return []

        embeddings: list[List[float]] = []
        total_batches = max(1, math.ceil(len(texts) / batch_size))
        iterator = range(0, len(texts), batch_size)
        for start in tqdm(
            iterator,
            total=total_batches,
            desc="Embedding batches",
            disable=total_batches <= 1,
        ):
            batch = texts[start : start + batch_size]
            for text in batch:
                embeddings.append(self.embed_text(text))
        return embeddings

    def get_query_embedding(self, query: str) -> List[float]:
        """Return an embedding configured for query semantics."""

        return self.embed_text(query, prefix="query: ")

    def get_document_embedding(self, text: str) -> List[float]:
        """Return an embedding configured for document storage semantics."""

        return self.embed_text(text, prefix="passage: ")

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    @property
    def total_embeddings(self) -> int:
        with self._metrics_lock:
            return self._total_embeddings

    @property
    def cache_hit_rate(self) -> float:
        with self._metrics_lock:
            if self._cache_lookups == 0:
                return 0.0
            return self._cache_hits / self._cache_lookups

    @property
    def average_latency_ms(self) -> float:
        with self._metrics_lock:
            if not self._latencies_ms:
                return 0.0
            return sum(self._latencies_ms) / len(self._latencies_ms)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _fetch_with_cache(self, text: str) -> tuple[List[float], bool]:
        info_before = self._cached_fetch.cache_info()
        vector = self._cached_fetch(text)
        info_after = self._cached_fetch.cache_info()

        hit_delta = info_after.hits - info_before.hits
        miss_delta = info_after.misses - info_before.misses
        cache_hit = hit_delta > 0 and miss_delta == 0

        if miss_delta > 0:
            self._logger.debug(
                "Cache miss for embedding segment.",
                extra={"context": {"operation": "embed_text", "segment_preview": text[:64]}},
            )
        return vector, cache_hit

    def _fetch_embedding_uncached(self, text: str) -> List[float]:
        def _request() -> List[float]:
            self._logger.debug(
                "Submitting NV-Embed request.",
                extra={
                    "context": {
                        "operation": "embed_text",
                        "segment_preview": text[:64],
                    }
                },
            )
            response = self._client.embeddings.create(
                model=self.MODEL_NAME,
                input=[text],
            )
            if not response.data:
                raise NIMServiceError("No embedding data returned from NV-Embed.")
            vector = response.data[0].embedding
            if len(vector) != self.EMBEDDING_DIMENSION:
                raise NIMServiceError(
                    f"Unexpected embedding dimensionality: {len(vector)} (expected {self.EMBEDDING_DIMENSION})."
                )
            return list(vector)

        try:
            return self._retryer(_request)
        except (RateLimitError, APITimeoutError, APIConnectionError, APIError, OpenAIError) as exc:
            self._log_exception("embed_text", exc, {"segment_preview": text[:64]})
            raise NIMServiceError("Failed to fetch embedding from NV-Embed.") from exc

    def _segment_text(self, text: str) -> List[str]:
        tokens = text.split()
        if len(tokens) <= self.MAX_TOKENS:
            return [text]

        segments = []
        for idx in range(0, len(tokens), self.MAX_TOKENS):
            chunk_tokens = tokens[idx : idx + self.MAX_TOKENS]
            segments.append(" ".join(chunk_tokens))
        return segments

    def _average_vectors(self, vectors: Iterable[List[float]]) -> List[float]:
        vectors = list(vectors)
        if not vectors:
            raise NIMServiceError("No vectors provided to average.")

        length = len(vectors[0])
        accumulator = [0.0] * length
        for vector in vectors:
            if len(vector) != length:
                raise NIMServiceError("Mismatched vector dimensionality during averaging.")
            for idx, value in enumerate(vector):
                accumulator[idx] += value

        count = float(len(vectors))
        return [value / count for value in accumulator]

    def _normalize(self, vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def _record_metrics(self, latency_ms: float) -> None:
        with self._metrics_lock:
            self._total_embeddings += 1
            self._latencies_ms.append(latency_ms)

    def _record_cache(self, cache_hit: bool) -> None:
        with self._metrics_lock:
            self._cache_lookups += 1
            if cache_hit:
                self._cache_hits += 1

    def _log_exception(
        self,
        operation: str,
        error: Exception,
        context: Optional[Dict[str, object]] = None,
    ) -> None:
        detail: Dict[str, object] = {"operation": operation}
        if context:
            detail.update(context)
        log_error(error, context=detail)
