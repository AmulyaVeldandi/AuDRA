from __future__ import annotations

from datetime import date, timedelta
import sys
import types
from typing import Any, Dict

import pytest

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
    exceptions_module = types.ModuleType("botocore.exceptions")

    class BotoCoreError(Exception):
        pass

    class NoCredentialsError(Exception):
        pass

    exceptions_module.BotoCoreError = BotoCoreError
    exceptions_module.NoCredentialsError = NoCredentialsError
    sys.modules["botocore.exceptions"] = exceptions_module

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
    exceptions_module = types.ModuleType("opensearchpy.exceptions")

    class OpenSearchException(Exception):
        pass

    class TransportError(Exception):
        pass

    class ConnectionError(Exception):
        pass

    exceptions_module.OpenSearchException = OpenSearchException
    exceptions_module.TransportError = TransportError
    exceptions_module.ConnectionError = ConnectionError
    sys.modules["opensearchpy.exceptions"] = exceptions_module

if "tqdm.auto" not in sys.modules:
    tqdm_module = types.ModuleType("tqdm.auto")

    def tqdm(iterable: Any, *args: Any, **kwargs: Any) -> Any:
        return iterable

    tqdm_module.tqdm = tqdm
    sys.modules["tqdm.auto"] = tqdm_module

if "slowapi" not in sys.modules:
    slowapi_module = types.ModuleType("slowapi")

    class _DummyLimiter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def limit(self, *args: Any, **kwargs: Any):
            def decorator(func):
                return func

            return decorator

    slowapi_module.Limiter = _DummyLimiter

    errors_module = types.ModuleType("slowapi.errors")

    class _DummyRateLimitExceeded(Exception):
        def __init__(self, detail: str = "Rate limit exceeded") -> None:
            super().__init__(detail)
            self.detail = detail

    errors_module.RateLimitExceeded = _DummyRateLimitExceeded
    slowapi_module.errors = errors_module

    sys.modules["slowapi"] = slowapi_module
    sys.modules["slowapi.errors"] = errors_module

if "slowapi.middleware" not in sys.modules:
    middleware_module = types.ModuleType("slowapi.middleware")

    class _DummySlowAPIMiddleware:
        def __init__(self, app: Any, **kwargs: Any) -> None:
            self.app = app

    middleware_module.SlowAPIMiddleware = _DummySlowAPIMiddleware
    sys.modules["slowapi.middleware"] = middleware_module

from src.api import app as app_module
from src.api.app import create_app
from src.api.models import RecommendationResponse
from src.api.routes import (
    _build_finding,
    _build_tasks,
    _clamp_confidence,
    health_check_endpoint,
)


class _DummyRequest:
    def __init__(self, app: Any) -> None:
        self.app = app


class _Pinger:
    def __init__(self, should_succeed: bool) -> None:
        self._result = should_succeed

    def ping(self) -> bool:
        return self._result


def test_clamp_confidence_handles_invalid_input() -> None:
    assert _clamp_confidence("0.8") == 0.8
    assert _clamp_confidence(None, default=0.42) == 0.42
    assert _clamp_confidence(5) == 1.0
    assert _clamp_confidence(-2) == 0.0


def test_build_finding_normalises_characteristics() -> None:
    payload = {
        "finding_id": "abc",
        "type": "nodule",
        "size_mm": "6",
        "location": "RUL",
        "characteristics": "spiculated",
        "confidence": "0.75",
    }
    finding = _build_finding(payload)
    assert finding.finding_id == "abc"
    assert finding.size_mm == 6.0
    assert finding.characteristics == ["spiculated"]
    assert finding.confidence == pytest.approx(0.75)


def test_build_tasks_generates_schedule_from_recommendations() -> None:
    today = date.today()
    orders = ["ORD-1", "ORD-2"]
    recommendations = [
        RecommendationResponse(
            recommendation_id="rec-1",
            follow_up_type="CT Chest",
            timeframe_months=3,
            urgency="urgent",
            reasoning="Guideline matched.",
            citation="Fleischner 2017",
            confidence=0.9,
        ),
        RecommendationResponse(
            recommendation_id="rec-2",
            follow_up_type="MRI Abdomen",
            timeframe_months=None,
            urgency="routine",
            reasoning="Incidental finding.",
            citation="ACR 2017",
            confidence=0.8,
        ),
    ]

    tasks = _build_tasks(orders, recommendations)
    assert len(tasks) == 2

    first = tasks[0]
    assert first.task_id == "ORD-1"
    assert first.procedure == "CT Chest"
    assert today < first.scheduled_date <= today + timedelta(days=90)

    second = tasks[1]
    assert second.task_id == "ORD-2"
    assert second.procedure == "MRI Abdomen"
    assert second.scheduled_date == today + timedelta(days=30)


@pytest.mark.asyncio
async def test_health_check_endpoint_reflects_service_states(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch heavy dependencies so the startup hook in create_app remains lightweight.
    class _DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    monkeypatch.setattr(app_module, "AuDRAAgent", _DummyAgent)
    monkeypatch.setattr(app_module, "NemotronClient", lambda: object())
    monkeypatch.setattr(app_module, "EmbeddingClient", lambda: object())

    class _DummyVectorStore:
        def __init__(self, index_name: str) -> None:
            self.index_name = index_name
            self._client = _Pinger(should_succeed=False)

    monkeypatch.setattr(app_module, "VectorStore", _DummyVectorStore)

    class _DummyEHR:
        use_mock = True

        def close(self) -> None:
            pass

    monkeypatch.setattr(app_module, "EHRClient", lambda use_mock=True: _DummyEHR())

    app = create_app()
    app.state.version = "test-version"
    app.state.llm_client = object()
    app.state.embedding_client = object()
    app.state.vector_store = _DummyVectorStore("medical_guidelines")
    app.state.ehr_client = None  # Force an unhealthy service.

    response = await health_check_endpoint(_DummyRequest(app))

    assert response.version == "test-version"
    assert response.status == "unhealthy"
    assert response.services["vector_store"] == "degraded"
    assert response.services["ehr"] == "unhealthy"
