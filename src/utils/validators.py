from __future__ import annotations

"""Input validation and sanitisation utilities."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

MEDICAL_KEYWORDS = {"findings", "impression", "technique"}
FHIR_REQUIRED_FIELDS = {
    "Patient": {"resourceType", "id"},
    "Observation": {"resourceType", "id", "status", "code", "subject"},
    "DiagnosticReport": {"resourceType", "id", "status", "code", "subject"},
    "ImagingStudy": {"resourceType", "id", "status", "subject", "series"},
}
PHI_FIELDS_TO_REMOVE = {
    "address",
    "dob",
    "date_of_birth",
    "birthdate",
    "phone",
    "email",
    "ssn",
}
NAME_FIELDS = {"name", "patient_name", "first_name", "last_name"}
MRN_FIELDS = {"mrn", "medical_record_number"}


def validate_report_text(text: str) -> Tuple[bool, str]:
    """Validate that the report text is sufficiently detailed and structured."""

    if not text or len(text.strip()) < 50:
        return False, "Report text is too short; minimum length is 50 characters."

    missing = [keyword for keyword in MEDICAL_KEYWORDS if keyword not in text.lower()]
    if missing:
        return False, f"Report text is missing required sections: {', '.join(sorted(missing))}."

    return True, ""


def validate_finding_size(size_mm: float) -> bool:
    """Validate that a finding size is within the expected clinical bounds."""

    try:
        value = float(size_mm)
    except (TypeError, ValueError):
        return False

    return 0 < value < 300


def validate_date_range(start: datetime, end: datetime) -> bool:
    """Validate that a date range is chronological and within a reasonable window."""

    if start is None or end is None:
        return False

    start_utc = _to_utc(start)
    end_utc = _to_utc(end)

    if end_utc <= start_utc:
        return False

    now = datetime.now(tz=timezone.utc)
    earliest_allowed = datetime(2000, 1, 1, tzinfo=timezone.utc)
    latest_allowed = now + timedelta(days=365)

    return earliest_allowed <= start_utc <= latest_allowed and earliest_allowed <= end_utc <= latest_allowed


def validate_fhir_resource(resource: dict[str, Any], resource_type: str) -> bool:
    """Validate the basic structure of a FHIR resource."""

    if not isinstance(resource, dict):
        return False

    if resource.get("resourceType") != resource_type:
        return False

    required_fields = FHIR_REQUIRED_FIELDS.get(resource_type, {"resourceType", "id"})
    if not required_fields.issubset(resource.keys()):
        return False

    return True


def sanitize_patient_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove or mask PHI attributes for safe logging."""

    if not isinstance(data, dict):
        return {}

    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        lower_key = key.lower()

        if lower_key in PHI_FIELDS_TO_REMOVE:
            continue

        if lower_key in NAME_FIELDS and isinstance(value, str):
            sanitized[key] = _hash_value(value)
            continue

        if lower_key in MRN_FIELDS and isinstance(value, str):
            sanitized[key] = _mask_mrn(value)
            continue

        if isinstance(value, dict):
            sanitized[key] = sanitize_patient_data(value)
            continue

        if isinstance(value, list):
            sanitized[key] = [_sanitize_list_item(item) for item in value]
            continue

        sanitized[key] = value

    return sanitized


def _hash_value(value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"hash:{digest}"


def _mask_mrn(value: str) -> str:
    trimmed = value.strip()
    last_four = trimmed[-4:] if len(trimmed) >= 4 else trimmed
    masked = "*" * max(len(trimmed) - len(last_four), 0)
    return f"{masked}{last_four}"


def _sanitize_list_item(item: Any) -> Any:
    if isinstance(item, dict):
        return sanitize_patient_data(item)
    if isinstance(item, list):
        return [_sanitize_list_item(sub_item) for sub_item in item]
    return item


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
