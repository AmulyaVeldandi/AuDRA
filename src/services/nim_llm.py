from __future__ import annotations

"""Client for the Nemotron NIM large language model service."""

import json
import threading
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Callable, Dict, Iterator, Optional

from jsonschema import ValidationError, validate
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils.config import get_settings
from src.utils.logger import get_logger, log_error, log_nim_call


class NIMServiceError(RuntimeError):
    """Raised when calls to the NVIDIA NIM service fail."""


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class NemotronClient:
    """Client wrapper for the NVIDIA Llama-3.1 Nemotron NIM."""

    MODEL_NAME = "meta/llama-3.1-nemotron-70b-instruct"
    REQUEST_TIMEOUT_SECONDS = 30.0

    def __init__(self) -> None:
        settings = get_settings()
        api_key = (
            settings.NIM_LLM_API_KEY.get_secret_value()
            if settings.NIM_LLM_API_KEY is not None
            else None
        )
        if not api_key:
            raise NIMServiceError("NIM LLM API key is not configured.")

        self._client = OpenAI(
            base_url=str(settings.NIM_LLM_ENDPOINT),
            api_key=api_key,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
        )

        self._logger = get_logger("audra.services.nim_llm")
        self._metrics_lock = threading.Lock()
        self._total_tokens = 0
        self._latencies_ms: list[float] = []
        self._total_calls = 0
        self._error_count = 0

        self._retryer = Retrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception_type(
                (RateLimitError, APITimeoutError, APIConnectionError, APIError)
            ),
            reraise=True,
        )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a text completion from the Nemotron model."""

        messages = self._build_messages(prompt, system_prompt=system_prompt)
        request_context = {
            "operation": "generate",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_preview": prompt[:200],
        }
        self._logger.debug("Submitting Nemotron generate request.", extra={"context": request_context})

        start_time = time.perf_counter()
        try:
            response = self._run_with_retry(
                lambda: self._client.chat.completions.create(
                    model=self.MODEL_NAME,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                operation="generate",
                context=request_context,
            )
        except NIMServiceError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._record_error()
            self._log_exception("generate", exc, request_context)
            raise NIMServiceError("Nemotron generate request failed.") from exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        usage = self._extract_usage(response)
        self._record_success(usage, latency_ms)

        content = self._first_choice_content(response)
        response_context = {
            "operation": "generate",
            "latency_ms": latency_ms,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "response_preview": (content or "")[:200],
        }
        self._logger.debug(
            "Received Nemotron generate response.", extra={"context": response_context}
        )
        self._log_nim_metrics(usage, latency_ms)
        return content or ""

    def generate_json(
        self,
        prompt: str,
        *,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Force a JSON response and validate the payload."""

        messages = self._build_messages(prompt)
        attempt = 0
        last_error: Exception | None = None

        while attempt < max_retries:
            attempt += 1
            attempt_context = {
                "operation": "generate_json",
                "attempt": attempt,
                "prompt_preview": prompt[:200],
            }
            self._logger.debug(
                "Submitting Nemotron JSON generation request.", extra={"context": attempt_context}
            )
            start_time = time.perf_counter()
            try:
                response = self._run_with_retry(
                    lambda: self._client.chat.completions.create(
                        model=self.MODEL_NAME,
                        messages=messages,
                        temperature=0.1,
                        response_format={"type": "json_object"},
                    ),
                    operation="generate_json",
                    context=attempt_context,
                )
            except NIMServiceError as exc:
                last_error = exc
                break
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
                self._record_error()
                self._log_exception("generate_json", exc, attempt_context)
                break

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            usage = self._extract_usage(response)
            self._record_success(usage, latency_ms)
            self._log_nim_metrics(usage, latency_ms)

            raw_content = self._first_choice_content(response) or ""
            try:
                payload = json.loads(raw_content)
            except JSONDecodeError as exc:
                last_error = exc
                self._logger.debug(
                    "Nemotron JSON decode failed; retrying.",
                    extra={
                        "context": {
                            "operation": "generate_json",
                            "attempt": attempt,
                            "error": str(exc),
                            "raw_preview": raw_content[:200],
                        }
                    },
                )
                continue

            if schema is not None:
                try:
                    validate(instance=payload, schema=schema)
                except ValidationError as exc:
                    last_error = exc
                    self._logger.debug(
                        "Nemotron JSON schema validation failed; retrying.",
                        extra={
                            "context": {
                                "operation": "generate_json",
                                "attempt": attempt,
                                "error": exc.message,
                            }
                        },
                    )
                    continue

            self._logger.debug(
                "Nemotron JSON generation succeeded.",
                extra={
                    "context": {
                        "operation": "generate_json",
                        "attempt": attempt,
                        "latency_ms": latency_ms,
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                    }
                },
            )
            return payload

        error = last_error or RuntimeError("Nemotron JSON generation failed.")
        self._record_error()
        self._log_exception(
            "generate_json",
            error,
            {
                "operation": "generate_json",
                "prompt_preview": prompt[:200],
                "attempts": attempt,
            },
        )
        raise NIMServiceError("Nemotron JSON generation failed.") from error

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream tokens back as they are produced."""

        temperature = 0.1
        max_tokens = 2048
        messages = self._build_messages(prompt, system_prompt=system_prompt)
        request_context = {
            "operation": "generate_stream",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_preview": prompt[:200],
        }
        self._logger.debug(
            "Submitting Nemotron streaming request.", extra={"context": request_context}
        )

        def _stream() -> Iterator[str]:
            start_time = time.perf_counter()
            prompt_tokens = 0
            completion_tokens = 0
            try:
                stream = self._run_with_retry(
                    lambda: self._client.chat.completions.create(
                        model=self.MODEL_NAME,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                    ),
                    operation="generate_stream",
                    context=request_context,
                )
            except NIMServiceError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error()
                self._log_exception("generate_stream", exc, request_context)
                raise NIMServiceError("Nemotron streaming request failed.") from exc

            success = True
            try:
                for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta if chunk.choices[0].delta else None
                        piece = (
                            delta.get("content")
                            if isinstance(delta, dict)
                            else getattr(delta, "content", None)
                        )
                        if piece:
                            yield piece
                    if getattr(chunk, "usage", None):
                        prompt_tokens = chunk.usage.prompt_tokens or prompt_tokens
                        completion_tokens = chunk.usage.completion_tokens or completion_tokens
            except Exception as exc:
                success = False
                self._record_error()
                self._log_exception("generate_stream", exc, request_context)
                raise NIMServiceError("Nemotron streaming request failed.") from exc
            finally:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                usage = _Usage(prompt_tokens, completion_tokens)
                if success:
                    self._record_success(usage, latency_ms)
                    self._log_nim_metrics(usage, latency_ms)
                    self._logger.debug(
                        "Nemotron streaming request completed.",
                        extra={
                            "context": {
                                "operation": "generate_stream",
                                "latency_ms": latency_ms,
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                            }
                        },
                    )

        return _stream()

    # --------------------------------------------------------------------- #
    # Metrics helpers
    # --------------------------------------------------------------------- #
    @property
    def total_tokens(self) -> int:
        with self._metrics_lock:
            return self._total_tokens

    @property
    def latencies_ms(self) -> list[float]:
        with self._metrics_lock:
            return list(self._latencies_ms)

    @property
    def error_rate(self) -> float:
        with self._metrics_lock:
            if self._total_calls == 0:
                return 0.0
            return self._error_count / self._total_calls

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _run_with_retry(
        self,
        func: Callable[[], Any],
        *,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        try:
            return self._retryer(func)
        except (RateLimitError, APITimeoutError, APIConnectionError, APIError) as exc:
            self._record_error()
            self._log_exception(operation, exc, context)
            raise NIMServiceError(f"Nemotron {operation} failed.") from exc
        except OpenAIError as exc:
            self._record_error()
            self._log_exception(operation, exc, context)
            raise NIMServiceError(f"Nemotron {operation} failed.") from exc

    def _record_success(self, usage: _Usage, latency_ms: float) -> None:
        with self._metrics_lock:
            self._total_calls += 1
            self._total_tokens += usage.total_tokens
            self._latencies_ms.append(latency_ms)

    def _record_error(self) -> None:
        with self._metrics_lock:
            self._error_count += 1
            self._total_calls += 1

    def _log_nim_metrics(self, usage: _Usage, latency_ms: float) -> None:
        log_nim_call(
            service="nemotron",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
        )

    def _log_exception(
        self,
        operation: str,
        error: Exception,
        context: Optional[Dict[str, Any]],
    ) -> None:
        detail = {"operation": operation}
        if context:
            detail.update(context)
        log_error(error, context=detail)

    @staticmethod
    def _extract_usage(response: Any) -> _Usage:
        usage = getattr(response, "usage", None)
        if usage:
            return _Usage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
        return _Usage()

    @staticmethod
    def _first_choice_content(response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        if not message:
            return None
        return message.get("content") if isinstance(message, dict) else getattr(message, "content", None)

    @staticmethod
    def _build_messages(prompt: str, *, system_prompt: Optional[str] = None) -> list[Dict[str, str]]:
        messages: list[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages
