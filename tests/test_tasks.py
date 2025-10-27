from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.tasks.fhir_builder import FHIRServiceRequestBuilder, format_fhir_date
from src.tasks.generator import TaskGenerator


def _sample_recommendation() -> dict[str, object]:
    return {
        "follow_up_type": "CT Chest without contrast",
        "timeframe_months": 6,
        "urgency": "urgent",
        "reasoning": "Follow Fleischner 2017 recommendations for subsolid nodules.",
        "citation": "Fleischner Society 2017",
    }


def _sample_finding() -> dict[str, object]:
    return {
        "finding_id": "finding-1",
        "finding_type": "nodule",
        "size_mm": 3.0,
        "location": "RUL",
        "characteristics": ["ground-glass"],
        "context": "3 mm ground-glass nodule in right upper lobe.",
    }


def test_generate_task_produces_expected_task() -> None:
    generator = TaskGenerator()
    recommendation = _sample_recommendation()
    finding = _sample_finding()

    task = generator.generate_task(recommendation, finding, patient_id="patient-001")

    assert task.patient_id == "patient-001"
    assert task.priority == "urgent"
    assert task.procedure_code["system"] == "CPT"
    assert task.procedure_code["code"] == "71250"
    assert task.scheduled_date > date.today()
    assert recommendation["reasoning"] in task.clinical_reason
    assert task.metadata["finding"]["finding_id"] == "finding-1"
    assert task.metadata["recommendation"]["follow_up_type"]


def test_calculate_scheduled_date_handles_end_of_month() -> None:
    generator = TaskGenerator()
    anchor = date(2024, 1, 31)
    scheduled = generator.calculate_scheduled_date(1, base_date=anchor)

    assert scheduled == date(2024, 2, 29)


def test_map_procedure_to_code_unknown_procedure_raises() -> None:
    generator = TaskGenerator()

    with pytest.raises(ValueError):
        generator.map_procedure_to_code("Unsupported Procedure")


def test_fhir_builder_constructs_service_request() -> None:
    generator = TaskGenerator()
    recommendation = _sample_recommendation()
    finding = _sample_finding()
    task = generator.generate_task(recommendation, finding, patient_id="patient-001")

    builder = FHIRServiceRequestBuilder()
    resource = builder.build_service_request(task, "report-123")

    assert resource["resourceType"] == "ServiceRequest"
    assert resource["id"] == task.task_id
    assert resource["code"]["coding"][0]["code"] == "71250"
    assert resource["subject"]["reference"] == "Patient/patient-001"
    assert resource["reasonReference"][0]["reference"] == "DiagnosticReport/report-123"
    assert resource["occurrenceTiming"]["event"][0] == format_fhir_date(task.scheduled_date)
    assert builder.validate_service_request(resource)


def test_build_timing_uses_default_month_estimate_when_timeframe_missing() -> None:
    builder = FHIRServiceRequestBuilder()
    scheduled = date.today() + timedelta(days=40)
    timing = builder.build_timing(scheduled, timeframe_months=None)

    assert timing["event"] == [format_fhir_date(scheduled)]
    assert timing["repeat"]["period"] >= 1
    assert "Scheduled in" in timing["code"]["text"]
