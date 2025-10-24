from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.parsers.fhir_models import CodeableConcept, Reference, Timing, TimingRepeat, ServiceRequest
from src.services.ehr_client import EHRClient


def test_mock_ehr_client_round_trip_service_request() -> None:
    with EHRClient() as client:
        request = ServiceRequest(
            id="temp-order",
            status="active",
            intent="order",
            code=CodeableConcept(text="CT Chest follow-up"),
            subject=Reference(reference="Patient/patient-123"),
            authoredOn=datetime.now(timezone.utc),
            occurrenceTiming=Timing(
                repeat=TimingRepeat(frequency=1, period=6, periodUnit="mo")
            ),
        )

        order_id = client.create_service_request(request)
        assert order_id != "temp-order"

        pending = client.list_pending_tasks("patient-123")
        order_ids = {task["order_id"] for task in pending}
        assert order_id in order_ids

        patient = client.get_patient("patient-123")
        assert patient.id == "patient-123"

        report_path = Path("data/sample_reports/chest_ct_ggo_fhir.json")
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        report_id = report_payload["id"]

        report = client.get_diagnostic_report(report_id)
        assert report.id == report_id
