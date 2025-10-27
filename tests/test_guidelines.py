from __future__ import annotations

import sys
import types
from typing import Any, Dict, List

if "openai" not in sys.modules:
    openai_module = types.ModuleType("openai")

    class _OpenAIBaseError(Exception):
        pass

    class APIConnectionError(_OpenAIBaseError):
        pass

    class APIError(_OpenAIBaseError):
        pass

    class APITimeoutError(_OpenAIBaseError):
        pass

    class OpenAIError(_OpenAIBaseError):
        pass

    class RateLimitError(_OpenAIBaseError):
        pass

    class OpenAI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    openai_module.APIConnectionError = APIConnectionError
    openai_module.APIError = APIError
    openai_module.APITimeoutError = APITimeoutError
    openai_module.OpenAIError = OpenAIError
    openai_module.RateLimitError = RateLimitError
    openai_module.OpenAI = OpenAI

    sys.modules["openai"] = openai_module

if "jsonschema" not in sys.modules:
    jsonschema_module = types.ModuleType("jsonschema")

    class ValidationError(Exception):
        pass

    def validate(instance: Any, schema: Any) -> None:
        return None

    jsonschema_module.ValidationError = ValidationError
    jsonschema_module.validate = validate
    sys.modules["jsonschema"] = jsonschema_module

if "boto3" not in sys.modules:
    boto3_module = types.ModuleType("boto3")

    class Session:
        def __init__(self, region_name: str | None = None) -> None:
            self.region_name = region_name

        def get_credentials(self) -> Any:
            class _Creds:
                access_key = "test"
                secret_key = "test"
                token = None

            return _Creds()

    boto3_module.Session = Session
    sys.modules["boto3"] = boto3_module

if "botocore" not in sys.modules:
    botocore_module = types.ModuleType("botocore")
    sys.modules["botocore"] = botocore_module

if "botocore.exceptions" not in sys.modules:
    botocore_exceptions = types.ModuleType("botocore.exceptions")

    class BotoCoreError(Exception):
        pass

    class NoCredentialsError(Exception):
        pass

    botocore_exceptions.BotoCoreError = BotoCoreError
    botocore_exceptions.NoCredentialsError = NoCredentialsError
    sys.modules["botocore.exceptions"] = botocore_exceptions

if "opensearchpy" not in sys.modules:
    opensearch_module = types.ModuleType("opensearchpy")

    class AWSV4SignerAuth:
        def __init__(self, credentials: Any, region: str, service: str = "aoss") -> None:
            self.credentials = credentials
            self.region = region
            self.service = service

    class RequestsHttpConnection:
        pass

    class OpenSearch:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.indices = types.SimpleNamespace(
                exists=lambda index: True,
                create=lambda **kwargs: None,
            )

        def index(self, *args: Any, **kwargs: Any) -> None:
            return None

        def search(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            return {"hits": {"hits": []}}

    def helpers_bulk(*args: Any, **kwargs: Any) -> tuple[list[object], list[object]]:
        return ([], [])

    opensearch_module.AWSV4SignerAuth = AWSV4SignerAuth
    opensearch_module.OpenSearch = OpenSearch
    opensearch_module.RequestsHttpConnection = RequestsHttpConnection
    opensearch_module.helpers = types.SimpleNamespace(bulk=helpers_bulk)

    sys.modules["opensearchpy"] = opensearch_module

if "opensearchpy.exceptions" not in sys.modules:
    opensearch_exceptions = types.ModuleType("opensearchpy.exceptions")

    class OpenSearchException(Exception):
        pass

    class TransportError(Exception):
        pass

    class ConnectionError(Exception):
        pass

    opensearch_exceptions.OpenSearchException = OpenSearchException
    opensearch_exceptions.TransportError = TransportError
    opensearch_exceptions.ConnectionError = ConnectionError
    sys.modules["opensearchpy.exceptions"] = opensearch_exceptions

if "tqdm.auto" not in sys.modules:
    tqdm_module = types.ModuleType("tqdm.auto")

    def tqdm(iterable: Any, *args: Any, **kwargs: Any) -> Any:
        return iterable

    tqdm_module.tqdm = tqdm
    sys.modules["tqdm.auto"] = tqdm_module

from src.guidelines.indexer import GuidelineChunk
from src.guidelines.retriever import GuidelineRetriever, RetrievedDocument


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.last_text: str | None = None

    def embed_text(self, text: str, prefix: str = "") -> List[float]:
        self.last_text = f"{prefix}{text}"
        return [0.1, 0.2, 0.3]


class _FakeVectorStore:
    def __init__(self) -> None:
        self.last_filters: Dict[str, Any] | None = None
        self.last_top_k: int | None = None
        self.last_query: List[float] | None = None

    def search(self, query: List[float], top_k: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.last_query = list(query)
        self.last_top_k = top_k
        self.last_filters = dict(filters)
        return [
            {
                "id": "chunk-1",
                "text": "6mm solid nodule in high risk patient. Recommend 3 month CT.",
                "score": 0.6,
                "metadata": {
                    "source": "Fleischner Society Pulmonary Nodule Recommendations (2017)",
                    "category": "Pulmonary nodules",
                    "size_min_mm": 6,
                    "size_max_mm": 8,
                    "risk_level": "high",
                    "recommendation": "CT chest in 3 months.",
                    "citation": "Fleischner 2017",
                },
            },
            {
                "id": "chunk-2",
                "text": "2mm low risk nodule -> annual follow-up.",
                "score": 0.9,
                "metadata": {
                    "source": "Fleischner Society Pulmonary Nodule Recommendations (2017)",
                    "category": "Pulmonary nodules",
                    "size_min_mm": 1,
                    "size_max_mm": 3,
                    "risk_level": "low",
                },
            },
        ]

    def hybrid_search(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        raise AssertionError("hybrid_search should not be called when filters exist.")


def _make_retriever() -> GuidelineRetriever:
    return GuidelineRetriever(_FakeEmbeddingClient(), _FakeVectorStore())


def test_build_query_text_uses_available_attributes() -> None:
    retriever = _make_retriever()
    finding = {
        "type": "Pulmonary nodule",
        "characteristics": ["ground-glass", "part-solid"],
        "size_mm": 6,
        "location": "RUL",
        "risk_level": "HIGH risk smoker",
    }

    text = retriever.build_query_text(finding)
    assert "Pulmonary nodule" in text
    assert "ground-glass" in text
    assert "part-solid" in text
    assert "6mm" in text
    assert "RUL" in text
    assert "high risk patient" in text
    assert text.endswith("follow-up recommendation")


def test_rerank_results_prioritises_matching_size_and_risk() -> None:
    retriever = _make_retriever()
    finding = {"size_mm": 6, "risk_level": "high"}
    candidate_far = RetrievedDocument(
        id="chunk-small",
        text="",
        score=0.9,
        metadata={"size_min_mm": 1, "size_max_mm": 3, "risk_level": "low"},
    )
    candidate_match = RetrievedDocument(
        id="chunk-match",
        text="",
        score=0.5,
        metadata={"size_min_mm": 5, "size_max_mm": 8, "risk_level": "high"},
    )

    ranked = retriever.rerank_results([candidate_far, candidate_match], finding)
    assert ranked[0].id == "chunk-match"
    assert ranked[0].score > ranked[1].score


def test_retrieve_applies_filters_and_returns_guideline_chunks() -> None:
    embedding_client = _FakeEmbeddingClient()
    vector_store = _FakeVectorStore()
    retriever = GuidelineRetriever(embedding_client, vector_store)

    finding = {
        "type": "Pulmonary nodule",
        "size_mm": 6,
        "risk_level": "high",
        "location": "RUL",
    }

    chunks = retriever.retrieve(finding, top_k=1)

    assert embedding_client.last_text is not None
    assert "Pulmonary nodule" in embedding_client.last_text
    assert vector_store.last_filters == {"finding_size": 6.0, "patient_risk": "high"}
    assert vector_store.last_top_k == 15

    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, GuidelineChunk)
    assert chunk.chunk_id == "chunk-1"
    assert chunk.source.startswith("Fleischner")
    assert chunk.recommendation == "CT chest in 3 months."
