"""FHIR R4 resource models used by the AuDRA radiology pipeline.

The models in this module provide a typed interface around a focused subset of
FHIR DiagnosticReport workflows. Each model offers helpers to convert to and
from native FHIR JSON representations while keeping validation rules close to
the HL7 specification.
"""

from __future__ import annotations

import base64
import binascii
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import Self


def _parse_datetime(value: Any) -> datetime:
    """Parse an ISO 8601 datetime string, supporting the trailing Z shorthand."""

    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Invalid ISO 8601 datetime: {value!r}") from exc
    raise TypeError(f"Expected datetime or str, received {type(value).__name__}")


def _parse_date(value: Any) -> date:
    """Parse an ISO 8601 date string."""

    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO 8601 date: {value!r}") from exc
    raise TypeError(f"Expected date or str, received {type(value).__name__}")


class FHIRBaseModel(BaseModel):
    """Base class for lightweight FHIR models with convenience helpers."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    def to_fhir(self) -> Dict[str, Any]:
        """Return the object as a FHIR-compatible JSON dictionary."""

        return self.model_dump(by_alias=True, exclude_none=True)

    @classmethod
    def from_fhir(cls, data: Dict[str, Any]) -> Self:
        """Instantiate the model from a FHIR JSON dictionary."""

        return cls.model_validate(data)


class Reference(FHIRBaseModel):
    """FHIR Reference type pointing to another resource.

    Example
    -------
    >>> Reference.from_fhir({"reference": "Patient/patient-1"}).to_fhir()
    {'reference': 'Patient/patient-1'}
    """

    reference: str = Field(..., min_length=1, description="Reference string such as Patient/123")
    display: Optional[str] = Field(default=None, description="Optional display label")

    @field_validator("reference")
    @classmethod
    def _ensure_reference(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("FHIR references must include a resourceType prefix (e.g. Patient/123)")
        return value


class Coding(FHIRBaseModel):
    """FHIR Coding structure capturing a system, code, and display text.

    Example
    -------
    >>> Coding.from_fhir({"system": "http://loinc.org", "code": "71250-2"}).to_fhir()
    {'system': 'http://loinc.org', 'code': '71250-2'}
    """

    system: Optional[str] = Field(default=None, description="URI of the code system")
    code: Optional[str] = Field(default=None, description="Code value within the system")
    display: Optional[str] = Field(default=None, description="Human-readable display")


class CodeableConcept(FHIRBaseModel):
    """FHIR CodeableConcept wrapper allowing text and structured codings.

    Example
    -------
    >>> CodeableConcept(
    ...     coding=[Coding(system="http://loinc.org", code="71250-2")],
    ...     text="CT Chest without contrast",
    ... ).to_fhir()
    {'coding': [{'system': 'http://loinc.org', 'code': '71250-2'}], 'text': 'CT Chest without contrast'}
    """

    coding: List[Coding] = Field(default_factory=list, description="List of coding entries")
    text: Optional[str] = Field(default=None, description="Plain-language representation")

    @field_validator("coding")
    @classmethod
    def _prune_empty_codings(cls, values: List[Coding]) -> List[Coding]:
        return [coding for coding in values if coding.model_dump(exclude_none=True)]


class Identifier(FHIRBaseModel):
    """FHIR Identifier for referencing MRNs or external IDs.

    Example
    -------
    >>> Identifier(system="http://hospital.org/mrn", value="12345").to_fhir()
    {'system': 'http://hospital.org/mrn', 'value': '12345'}
    """

    system: Optional[str] = Field(default=None, description="Namespace for the identifier")
    value: str = Field(..., min_length=1, description="Identifier value")


class HumanName(FHIRBaseModel):
    """FHIR HumanName supporting family and given names.

    Example
    -------
    >>> HumanName(family="Doe", given=["Jane"]).to_fhir()
    {'family': 'Doe', 'given': ['Jane']}
    """

    family: Optional[str] = Field(default=None, description="Family name (surname)")
    given: List[str] = Field(default_factory=list, description="List of given names")

    @field_validator("given")
    @classmethod
    def _strip_given(cls, values: List[str]) -> List[str]:
        return [value.strip() for value in values if value.strip()]


class Attachment(FHIRBaseModel):
    """FHIR Attachment representing inline or referenced binary content.

    Example
    -------
    >>> Attachment(contentType="text/plain", data=base64.b64encode(b"hello").decode()).to_fhir()
    {'contentType': 'text/plain', 'data': 'aGVsbG8='}
    """

    contentType: Optional[str] = Field(default=None, description="MIME type of the attachment")
    url: Optional[str] = Field(default=None, description="URL to retrieve the content")
    data: Optional[str] = Field(default=None, description="Base64-encoded inline data")
    title: Optional[str] = Field(default=None, description="Human-readable title")
    language: Optional[str] = Field(default=None, description="BCP-47 language code")
    creation: Optional[datetime] = Field(default=None, description="When the attachment was created")

    @field_validator("data")
    @classmethod
    def _validate_base64(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Attachment.data must be base64 encoded") from exc
        return value.strip()

    @field_validator("creation", mode="before")
    @classmethod
    def _coerce_creation(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        return _parse_datetime(value)


class TimingRepeat(FHIRBaseModel):
    """FHIR Timing.repeat component capturing scheduling cadence.

    Example
    -------
    >>> TimingRepeat(frequency=1, period=6, periodUnit="mo").to_fhir()
    {'frequency': 1, 'period': 6.0, 'periodUnit': 'mo'}
    """

    frequency: Optional[int] = Field(default=None, ge=1, description="Number of times per period")
    period: Optional[float] = Field(default=None, gt=0.0, description="Period length")
    periodUnit: Optional[Literal["s", "min", "h", "d", "wk", "mo", "a"]] = Field(
        default=None, description="Unit of time for the period"
    )


class Timing(FHIRBaseModel):
    """FHIR Timing structure describing when an action should occur.

    Example
    -------
    >>> Timing(
    ...     repeat=TimingRepeat(frequency=1, period=12, periodUnit="mo"),
    ... ).to_fhir()
    {'repeat': {'frequency': 1, 'period': 12.0, 'periodUnit': 'mo'}}
    """

    event: Optional[List[datetime]] = Field(
        default=None, description="Specific times when the event should occur"
    )
    repeat: Optional[TimingRepeat] = Field(default=None, description="Repeat details")
    code: Optional[CodeableConcept] = Field(default=None, description="Meaning of the timing schedule")

    @field_validator("event", mode="before")
    @classmethod
    def _coerce_event(cls, value: Any) -> Optional[List[datetime]]:
        if value is None:
            return None
        if not isinstance(value, list):
            raise TypeError("Timing.event must be a list")
        return [_parse_datetime(item) for item in value]


class Annotation(FHIRBaseModel):
    """FHIR Annotation capturing free-text notes.

    Example
    -------
    >>> Annotation(text="Follow-up in 6 months.").to_fhir()
    {'text': 'Follow-up in 6 months.'}
    """

    authorReference: Optional[Reference] = Field(default=None, description="Reference to the author")
    authorString: Optional[str] = Field(default=None, description="Free text author name")
    time: Optional[datetime] = Field(default=None, description="When the note was made")
    text: str = Field(..., min_length=1, description="Annotation text")

    @field_validator("time", mode="before")
    @classmethod
    def _coerce_time(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        return _parse_datetime(value)


class DiagnosticReport(FHIRBaseModel):
    """FHIR DiagnosticReport focusing on imaging results.

    Example
    -------
    >>> resource = DiagnosticReport.from_fhir({
    ...     "resourceType": "DiagnosticReport",
    ...     "id": "report-1",
    ...     "status": "final",
    ...     "code": {"text": "CT Chest"},
    ...     "subject": {"reference": "Patient/patient-1"},
    ...     "effectiveDateTime": "2024-06-01T12:00:00Z",
    ...     "conclusion": "No acute thoracic abnormality."
    ... })
    >>> resource.to_fhir()["status"]
    'final'
    """

    id: str = Field(..., min_length=1, description="Unique DiagnosticReport identifier")
    status: Literal["registered", "partial", "preliminary", "final"] = Field(
        ..., description="Workflow status of the report"
    )
    code: CodeableConcept = Field(..., description="Imaging modality and coding")
    subject: Reference = Field(..., description="Reference to the patient resource")
    effectiveDateTime: datetime = Field(..., description="When the study was performed")
    conclusion: Optional[str] = Field(default=None, description="Narrative report text")
    presentedForm: Optional[List[Attachment]] = Field(
        default=None, description="Attachments such as PDFs or structured documents"
    )

    @field_validator("effectiveDateTime", mode="before")
    @classmethod
    def _coerce_effective(cls, value: Any) -> datetime:
        return _parse_datetime(value)

    def to_fhir(self) -> Dict[str, Any]:
        payload = super().to_fhir()
        payload["resourceType"] = "DiagnosticReport"
        payload["effectiveDateTime"] = self.effectiveDateTime.isoformat()
        return payload

    @classmethod
    def from_fhir(cls, data: Dict[str, Any]) -> Self:
        if data.get("resourceType") != "DiagnosticReport":
            raise ValueError("Expected resourceType 'DiagnosticReport'")
        return super().from_fhir(data)


class Patient(FHIRBaseModel):
    """FHIR Patient resource capturing demographic context.

    Example
    -------
    >>> patient = Patient(
    ...     id="patient-123",
    ...     identifier=[Identifier(system="http://hospital.org/mrn", value="MRN123")],
    ...     name=[HumanName(family="Doe", given=["Jane"])],
    ...     birthDate=date(1982, 4, 15),
    ...     gender="female",
    ... )
    >>> patient.to_fhir()["resourceType"]
    'Patient'
    """

    id: str = Field(..., min_length=1, description="Unique patient identifier")
    identifier: List[Identifier] = Field(default_factory=list, description="External identifiers (e.g. MRN)")
    name: List[HumanName] = Field(default_factory=list, description="Patient names")
    birthDate: date = Field(..., description="Date of birth")
    gender: Literal["male", "female", "other", "unknown"] = Field(
        ..., description="Administrative gender"
    )

    @field_validator("birthDate", mode="before")
    @classmethod
    def _coerce_birthdate(cls, value: Any) -> date:
        return _parse_date(value)

    def to_fhir(self) -> Dict[str, Any]:
        payload = super().to_fhir()
        payload["resourceType"] = "Patient"
        payload["birthDate"] = self.birthDate.isoformat()
        return payload

    @classmethod
    def from_fhir(cls, data: Dict[str, Any]) -> Self:
        if data.get("resourceType") != "Patient":
            raise ValueError("Expected resourceType 'Patient'")
        return super().from_fhir(data)


class ServiceRequest(FHIRBaseModel):
    """FHIR ServiceRequest describing follow-up imaging orders.

    Example
    -------
    >>> ServiceRequest(
    ...     id="order-1",
    ...     status="active",
    ...     intent="order",
    ...     code=CodeableConcept(text="CT Chest follow-up"),
    ...     subject=Reference(reference="Patient/patient-123"),
    ...     authoredOn=datetime(2024, 6, 1, 12, 0),
    ...     occurrenceTiming=Timing(repeat=TimingRepeat(frequency=1, period=6, periodUnit="mo")),
    ... ).to_fhir()["status"]
    'active'
    """

    id: str = Field(..., min_length=1, description="Unique ServiceRequest identifier")
    status: Literal["draft", "active", "completed"] = Field(..., description="Lifecycle status")
    intent: Literal["order", "plan"] = Field(..., description="Intent of the request")
    code: CodeableConcept = Field(..., description="Requested service or procedure")
    subject: Reference = Field(..., description="Patient reference")
    authoredOn: datetime = Field(..., description="When the order was authored")
    occurrenceTiming: Timing = Field(..., description="Scheduling details")
    reasonReference: Optional[Reference] = Field(
        default=None, description="Reference to a supporting DiagnosticReport"
    )
    note: Optional[List[Annotation]] = Field(default=None, description="Clinical notes")

    @field_validator("authoredOn", mode="before")
    @classmethod
    def _coerce_authored_on(cls, value: Any) -> datetime:
        return _parse_datetime(value)

    def to_fhir(self) -> Dict[str, Any]:
        payload = super().to_fhir()
        payload["resourceType"] = "ServiceRequest"
        payload["authoredOn"] = self.authoredOn.isoformat()
        return payload

    @classmethod
    def from_fhir(cls, data: Dict[str, Any]) -> Self:
        if data.get("resourceType") != "ServiceRequest":
            raise ValueError("Expected resourceType 'ServiceRequest'")
        return super().from_fhir(data)
