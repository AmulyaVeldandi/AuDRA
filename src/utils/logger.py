from __future__ import annotations

"""Structured logging helpers for the AuDRA-Rad project."""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.utils.config import get_settings


_thread_local = threading.local()
_configured = False


class CorrelationIdFilter(logging.Filter):
    """Ensure every log record carries a correlation identifier."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - required signature
        record.correlation_id = getattr(_thread_local, "correlation_id", "-")
        return True


class JsonFormatter(logging.Formatter):
    """Formatter that emits structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - required signature
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }

        context = getattr(record, "context", None)
        if context is not None:
            payload["context"] = context

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class DevFormatter(logging.Formatter):
    """Human-readable formatter intended for local development."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def __init__(self) -> None:
        super().__init__()
        self._formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s (%(correlation_id)s) - %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - required signature
        formatted = self._formatter.format(record)
        color = self.COLORS.get(record.levelname, "")
        if color:
            formatted = f"{color}{formatted}{self.RESET}"
        context = getattr(record, "context", None)
        if context is not None:
            formatted = f"{formatted}\n    context: {context}"
        if record.exc_info:
            formatted = f"{formatted}\n    {self.formatException(record.exc_info)}"
        return formatted


def set_correlation_id(correlation_id: Optional[str]) -> None:
    """Bind a correlation identifier to the current thread."""

    if correlation_id:
        _thread_local.correlation_id = correlation_id
    elif hasattr(_thread_local, "correlation_id"):
        delattr(_thread_local, "correlation_id")


def get_correlation_id() -> Optional[str]:
    """Return the correlation identifier bound to the current thread."""

    return getattr(_thread_local, "correlation_id", None)


def clear_correlation_id() -> None:
    """Remove any correlation identifier bound to the current thread."""

    if hasattr(_thread_local, "correlation_id"):
        delattr(_thread_local, "correlation_id")


def configure_logging() -> None:
    """Configure the global logging system."""

    global _configured  # noqa: PLW0603 - intended module-level state
    if _configured:
        return

    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())

    if settings.ENVIRONMENT == "dev":
        handler.setFormatter(DevFormatter())
    else:
        handler.setFormatter(JsonFormatter())

    root_logger.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for the application."""

    configure_logging()
    return logging.getLogger(name)


def _emit_with_context(
    level: int,
    message: str,
    *,
    logger_name: str,
    context: Optional[Dict[str, Any]] = None,
    exc_info: Any = None,
) -> None:
    logger = get_logger(logger_name)
    log_kwargs: Dict[str, Any] = {}
    if context is not None:
        log_kwargs["extra"] = {"context": context}
    if exc_info:
        log_kwargs["exc_info"] = exc_info
    logger.log(level, message, **log_kwargs)


def log_agent_step(
    step_name: str,
    input_data: Any,
    output_data: Any,
    duration_ms: float,
    correlation_id: Optional[str] = None,
) -> None:
    """Emit a structured log entry for an agent step."""

    previous = get_correlation_id()
    if correlation_id:
        set_correlation_id(correlation_id)

    context = {
        "step": step_name,
        "input": input_data,
        "output": output_data,
        "duration_ms": duration_ms,
    }
    try:
        _emit_with_context(
            logging.INFO,
            f"Agent step '{step_name}' completed.",
            logger_name="audra.agent",
            context=context,
        )
    finally:
        if correlation_id:
            set_correlation_id(previous)


def log_nim_call(
    service: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    correlation_id: Optional[str] = None,
) -> None:
    """Log metrics from a call to the NVIDIA NIM service."""

    previous = get_correlation_id()
    if correlation_id:
        set_correlation_id(correlation_id)

    context = {
        "service": service,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
    }
    try:
        _emit_with_context(
            logging.DEBUG,
            f"NIM call '{service}' completed.",
            logger_name="audra.nim",
            context=context,
        )
    finally:
        if correlation_id:
            set_correlation_id(previous)


def log_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    stack_trace: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Emit a structured error log with optional context and stack trace."""

    previous = get_correlation_id()
    if correlation_id:
        set_correlation_id(correlation_id)

    merged_context = context.copy() if context else {}
    merged_context.update({"error": str(error)})
    if stack_trace:
        merged_context["stack_trace"] = stack_trace

    try:
        _emit_with_context(
            logging.ERROR,
            "An error occurred.",
            logger_name="audra.error",
            context=merged_context,
            exc_info=(type(error), error, error.__traceback__) if stack_trace is None else None,
        )
    finally:
        if correlation_id:
            set_correlation_id(previous)
