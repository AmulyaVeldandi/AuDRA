"""Pydantic request and response models for the AuDRA API layer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class ProcessReportRequest(BaseModel):
    """Inbound payload for processing a single radiology report."""

    report_text: str = Field(
        ...,
        min_length=50,
        description="Radiology report text to analyse.",
    )
    patient_id: Optional[str] = Field(
        default=None,
        description="Patient MRN or identifier.",
    )
    patient_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context (age, risk_factors, smoking_history, etc.).",
    )
    report_id: Optional[str] = Field(
        default=None,
        description="Identifier for the submitted report.",
    )
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional execution flags (auto_create_tasks, trace_depth, etc.).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_text": (
                    "FINDINGS: 3mm ground-glass opacity in the right upper lobe. "
                    "No pleural effusion. IMPRESSION: Indeterminate pulmonary "
                    "nodule requires interval follow-up."
                ),
                "patient_id": "MRN123456",
                "patient_context": {"age": 65, "smoking_history": "40 pack-years"},
                "report_id": "RPT-2024-10-001",
                "options": {"auto_create_tasks": True},
            }
        }
    )

    @field_validator("report_text")
    @classmethod
    def _validate_report_text(cls, value: str) -> str:
        """Enforce a minimum length after trimming whitespace."""

        normalized = value.strip()
        if len(normalized) < 50:
            raise ValueError("report_text must contain at least 50 characters of content.")
        return normalized


class BatchProcessRequest(BaseModel):
    """Inbound payload for processing a batch of reports."""

    reports: List[ProcessReportRequest] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Collection of reports to process (max 10).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reports": [
                    {
                        "report_text": (
                            "FINDINGS: New 8mm part-solid nodule in LLL. "
                            "IMPRESSION: Recommend 3 month follow-up CT."
                        ),
                        "patient_id": "MRN987654",
                        "patient_context": {"age": 58, "copd": True},
                        "report_id": "RPT-2024-10-010",
                    }
                ]
            }
        }
    )


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


HealthStatus = Literal["healthy", "degraded", "unhealthy"]
ProcessingStatus = Literal["success", "no_findings", "requires_review", "error"]
UrgencyLevel = Literal["routine", "priority", "urgent", "stat"]


class FindingResponse(BaseModel):
    """Structured representation of an identified finding."""

    finding_id: str = Field(..., description="Unique identifier for the finding.")
    type: str = Field(..., description="Finding category (e.g., nodule, effusion).")
    size_mm: Optional[float] = Field(
        default=None,
        ge=0,
        description="Measured size in millimetres (if applicable).",
    )
    location: str = Field(..., description="Anatomical location of the finding.")
    characteristics: List[str] = Field(
        default_factory=list,
        description="Relevant attributes (spiculated, ground-glass, etc.).",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0 and 1.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "finding_id": "finding-001",
                "type": "pulmonary_nodule",
                "size_mm": 6.5,
                "location": "Right upper lobe",
                "characteristics": ["ground-glass", "part-solid"],
                "confidence": 0.92,
            }
        }
    )


class RecommendationResponse(BaseModel):
    """Recommendation derived from guidelines and reasoning."""

    recommendation_id: str = Field(..., description="Unique identifier for the recommendation.")
    follow_up_type: str = Field(..., description="Recommended follow-up procedure.")
    timeframe_months: Optional[int] = Field(
        default=None,
        ge=0,
        description="Recommended follow-up window in months.",
    )
    urgency: UrgencyLevel = Field(
        ...,
        description="Clinical urgency for the follow-up action.",
    )
    reasoning: str = Field(..., description="Summary of the decision rationale.")
    citation: str = Field(..., description="Supporting guideline citation.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0 and 1.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "recommendation_id": "rec-123",
                "follow_up_type": "Low-dose CT chest",
                "timeframe_months": 6,
                "urgency": "priority",
                "reasoning": "Solid nodule >6mm in high-risk patient warrants 6-month CT.",
                "citation": "Fleischner Society 2017 - Table 2",
                "confidence": 0.88,
            }
        }
    )


class TaskResponse(BaseModel):
    """Details of a follow-up task created in the EHR."""

    task_id: str = Field(..., description="Identifier for the generated task.")
    procedure: str = Field(..., description="Procedure or order description.")
    scheduled_date: date = Field(..., description="Planned date for the procedure.")
    reason: str = Field(..., description="Clinical justification for the task.")
    order_id: Optional[str] = Field(
        default=None,
        description="EHR order identifier if created.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "task-789",
                "procedure": "Low-dose CT chest",
                "scheduled_date": "2025-03-15",
                "reason": "6mm part-solid nodule with high-risk features.",
                "order_id": "RAD-20250101-1234",
            }
        }
    )

    @field_validator("scheduled_date")
    @classmethod
    def _validate_future_date(cls, value: date) -> date:
        """Ensure scheduled dates are in the future."""

        today = date.today()
        if value <= today:
            raise ValueError("scheduled_date must be in the future.")
        return value


class ProcessReportResponse(BaseModel):
    """Full response for processing a single report."""

    status: ProcessingStatus = Field(..., description="Outcome status of the processing run.")
    session_id: str = Field(..., description="Identifier for the processing session.")
    report_id: str = Field(..., description="Identifier for the processed report.")
    findings: List[FindingResponse] = Field(
        default_factory=list,
        description="Detected radiology findings.",
    )
    recommendations: List[RecommendationResponse] = Field(
        default_factory=list,
        description="Follow-up recommendations derived from findings.",
    )
    tasks: List[TaskResponse] = Field(
        default_factory=list,
        description="Created tasks/orders for follow-up actions.",
    )
    processing_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Total processing time in milliseconds.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional human-readable status message.",
    )
    requires_human_review: bool = Field(
        ...,
        description="Indicates if manual review is recommended.",
    )
    decision_trace: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Detailed reasoning trace emitted by the agent.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "session_id": "session-001",
                "report_id": "RPT-2024-10-001",
                "findings": [
                    {
                        "finding_id": "finding-001",
                        "type": "pulmonary_nodule",
                        "size_mm": 6.5,
                        "location": "Right upper lobe",
                        "characteristics": ["ground-glass"],
                        "confidence": 0.92,
                    }
                ],
                "recommendations": [
                    {
                        "recommendation_id": "rec-123",
                        "follow_up_type": "Low-dose CT chest",
                        "timeframe_months": 6,
                        "urgency": "priority",
                        "reasoning": "Guidelines recommend 6 month follow-up.",
                        "citation": "Fleischner Society 2017 - Table 2",
                        "confidence": 0.88,
                    }
                ],
                "tasks": [
                    {
                        "task_id": "task-789",
                        "procedure": "Low-dose CT chest",
                        "scheduled_date": "2025-03-15",
                        "reason": "6mm part-solid nodule with high-risk features.",
                        "order_id": "RAD-20250101-1234",
                    }
                ],
                "processing_time_ms": 742.5,
                "message": "Follow-up recommended.",
                "requires_human_review": False,
            }
        }
    )


class ErrorResponse(BaseModel):
    """Standard error envelope for API failures."""

    error_code: str = Field(..., description="Machine-readable error identifier.")
    message: str = Field(..., description="Human-readable error description.")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional object with additional error details.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="Timestamp when the error occurred.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": "VALIDATION_ERROR",
                "message": "report_text must contain at least 50 characters of content.",
                "details": {"field": "report_text"},
                "timestamp": "2025-01-05T12:00:00Z",
            }
        }
    )


class HealthResponse(BaseModel):
    """Response payload for service health checks."""

    status: HealthStatus = Field(..., description="Aggregate health status.")
    services: Dict[str, HealthStatus] = Field(
        ...,
        description="Health status for dependent services (LLM, embeddings, vector_store, EHR).",
    )
    version: str = Field(..., description="Application version string.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="Timestamp of the health check.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "services": {
                    "llm": "healthy",
                    "embeddings": "healthy",
                    "vector_store": "degraded",
                    "ehr": "healthy",
                },
                "version": "1.0.0",
                "timestamp": "2025-01-05T12:00:00Z",
            }
        }
    )
