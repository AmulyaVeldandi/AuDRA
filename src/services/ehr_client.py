from __future__ import annotations

"""Mockable FHIR EHR client used for demos and local development."""

import json
import random
import threading
import time
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import httpx
from pydantic import ValidationError

from src.parsers.fhir_models import (
    DiagnosticReport,
    HumanName,
    Identifier,
    Patient,
    ServiceRequest,
)
from src.utils.logger import get_logger

FHIRServiceRequest = ServiceRequest
FHIRPatient = Patient
FHIRDiagnosticReport = DiagnosticReport

AUDIT_LOGGER = get_logger("audra.audit")
LOGGER = get_logger(__name__)


class EHRClient:
    """Simulates a minimal subset of an Epic/Cerner FHIR client."""

    _MIN_LATENCY_MS = 50
    _MAX_LATENCY_MS = 200

    def __init__(self, base_url: str = "http://mock-ehr.local", use_mock: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.use_mock = use_mock

        self._lock = threading.Lock()
        self._rng = random.Random()

        self._service_requests: Dict[str, ServiceRequest] = {}
        self._patients: Dict[str, Patient] = {}
        self._diagnostic_reports: Dict[str, DiagnosticReport] = {}

        self._sample_dir = Path(__file__).resolve().parents[2] / "data" / "sample_reports"
        self._http_client: Optional[httpx.Client] = None

        if self.use_mock:
            self._load_mock_data()
            self._seed_default_patient()
        else:
            self._http_client = httpx.Client(base_url=self.base_url, timeout=10.0)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def create_service_request(self, service_request: Union[FHIRServiceRequest, Dict[str, Any]]) -> str:
        """Create a ServiceRequest resource and return the generated order identifier."""

        request_model = self._coerce_service_request(service_request)

        self._audit("service_request.create", {"patient": request_model.subject.reference})
        self._simulate_latency()

        if self.use_mock:
            order_id = self._generate_order_id()
            with self._lock:
                request_model.id = order_id
                self._service_requests[order_id] = request_model
            self._audit(
                "service_request.stored",
                {
                    "order_id": order_id,
                    "code": request_model.code.text or None,
                    "status": request_model.status,
                },
            )
            return order_id

        assert self._http_client is not None  # pragma: no cover - defensive
        payload = request_model.to_fhir()
        response = self._http_client.post("/ServiceRequest", json=payload)
        response.raise_for_status()
        body = response.json()
        order_id = self._extract_resource_id(body, response.headers.get("Location"))
        self._audit("service_request.remote", {"order_id": order_id})
        return order_id

    def get_patient(self, patient_id: str) -> FHIRPatient:
        """Return patient demographics for the given identifier."""

        self._audit("patient.read", {"patient_id": patient_id})
        self._simulate_latency()

        if self.use_mock:
            patient = self._patients.get(patient_id) or self._patients.get("patient-demo")
            if patient is None:
                raise KeyError(f"No mock patient available for '{patient_id}'.")
            return patient

        assert self._http_client is not None  # pragma: no cover - defensive
        response = self._http_client.get(f"/Patient/{patient_id}")
        response.raise_for_status()
        data = response.json()
        try:
            return Patient.from_fhir(data)
        except (ValueError, ValidationError) as exc:  # pragma: no cover - defensive
            LOGGER.error(
                "Failed to parse Patient resource from EHR.",
                extra={"context": {"error": str(exc), "patient_id": patient_id}},
            )
            raise

    def get_diagnostic_report(self, report_id: str) -> FHIRDiagnosticReport:
        """Return a DiagnosticReport by identifier."""

        self._audit("diagnostic_report.read", {"report_id": report_id})
        self._simulate_latency()

        if self.use_mock:
            report = self._diagnostic_reports.get(report_id)
            if report is None:
                report = self._load_single_report(report_id)
            if report is None:
                raise KeyError(f"No mock DiagnosticReport available for '{report_id}'.")
            return report

        assert self._http_client is not None  # pragma: no cover - defensive
        response = self._http_client.get(f"/DiagnosticReport/{report_id}")
        response.raise_for_status()
        data = response.json()
        try:
            return DiagnosticReport.from_fhir(data)
        except (ValueError, ValidationError) as exc:  # pragma: no cover - defensive
            LOGGER.error(
                "Failed to parse DiagnosticReport resource from EHR.",
                extra={"context": {"error": str(exc), "report_id": report_id}},
            )
            raise

    def list_pending_tasks(self, patient_id: str) -> List[Dict[str, Any]]:
        """Return outstanding ServiceRequests for the given patient."""

        self._audit("service_request.list", {"patient_id": patient_id})
        self._simulate_latency()

        if self.use_mock:
            tasks: List[Dict[str, Any]] = []
            with self._lock:
                for order_id, request in self._service_requests.items():
                    subject_id = (request.subject.reference or "").split("/")[-1]
                    if subject_id != patient_id:
                        continue
                    if request.status not in {"draft", "active"}:
                        continue
                    tasks.append(
                        {
                            "order_id": order_id,
                            "patient_id": subject_id,
                            "status": request.status,
                            "intent": request.intent,
                            "code": request.code.text or None,
                            "authored_on": request.authoredOn.isoformat(),
                            "occurrence": request.occurrenceTiming.to_fhir(),
                        }
                    )
            self._audit("service_request.list.completed", {"count": len(tasks)})
            return tasks

        assert self._http_client is not None  # pragma: no cover - defensive
        response = self._http_client.get(
            "/ServiceRequest",
            params={"patient": patient_id, "status": "active"},
        )
        response.raise_for_status()
        bundle = response.json()
        entries = bundle.get("entry", [])
        tasks: List[Dict[str, Any]] = []
        for entry in entries:
            resource = entry.get("resource", {})
            try:
                request = ServiceRequest.from_fhir(resource)
            except (ValueError, ValidationError) as exc:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Skipping invalid ServiceRequest in remote response.",
                    extra={"context": {"error": str(exc)}},
                )
                continue
            tasks.append(
                {
                    "order_id": request.id,
                    "patient_id": patient_id,
                    "status": request.status,
                    "intent": request.intent,
                    "code": request.code.text or None,
                    "authored_on": request.authoredOn.isoformat(),
                    "occurrence": request.occurrenceTiming.to_fhir(),
                }
            )
        self._audit("service_request.list.completed", {"count": len(tasks)})
        return tasks

    def close(self) -> None:
        """Release any HTTP resources."""

        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    # ------------------------------------------------------------------ #
    # Context manager helpers
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "EHRClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - context manager contract
        self.close()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _coerce_service_request(
        self, service_request: Union[FHIRServiceRequest, Dict[str, Any]]
    ) -> FHIRServiceRequest:
        if isinstance(service_request, ServiceRequest):
            return service_request
        if isinstance(service_request, dict):
            return ServiceRequest.from_fhir(service_request)
        raise TypeError("Service request must be a ServiceRequest model or FHIR JSON dictionary.")

    def _simulate_latency(self) -> None:
        delay = self._rng.uniform(self._MIN_LATENCY_MS, self._MAX_LATENCY_MS) / 1000.0
        time.sleep(delay)

    def _generate_order_id(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = self._rng.randint(1000, 9999)
        return f"RAD-{timestamp}-{suffix}"

    def _seed_default_patient(self) -> None:
        if self._patients:
            return
        demo_patient = Patient(
            id="patient-demo",
            identifier=[
                Identifier(system="http://mock-ehr.local/mrn", value="MRN-DEMO-001"),
            ],
            name=[HumanName(family="Demo", given=["Patient"])],
            birthDate=date(1985, 1, 1),
            gender="female",
        )
        self._patients[demo_patient.id] = demo_patient

    def _load_mock_data(self) -> None:
        if not self._sample_dir.exists():
            LOGGER.debug(
                "Sample directory for mock EHR data not found.",
                extra={"context": {"path": str(self._sample_dir)}},
            )
            return

        for path in self._sample_dir.glob("*_fhir.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.warning(
                    "Failed to read mock DiagnosticReport file.",
                    extra={"context": {"path": str(path), "error": str(exc)}},
                )
                continue
            try:
                report = DiagnosticReport.from_fhir(payload)
            except (ValueError, ValidationError) as exc:
                LOGGER.warning(
                    "Skipping invalid DiagnosticReport sample.",
                    extra={"context": {"path": str(path), "error": str(exc)}},
                )
                continue
            self._diagnostic_reports[report.id] = report

            for resource in self._iter_contained(payload):
                if resource.get("resourceType") != "Patient":
                    continue
                try:
                    patient = Patient.from_fhir(resource)
                except (ValueError, ValidationError) as exc:
                    LOGGER.warning(
                        "Skipping invalid contained Patient sample.",
                        extra={"context": {"path": str(path), "error": str(exc)}},
                    )
                    continue
                self._patients.setdefault(patient.id, patient)

    def _iter_contained(self, payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        contained = payload.get("contained", [])
        if isinstance(contained, list):
            for resource in contained:
                if isinstance(resource, dict):
                    yield resource

    def _load_single_report(self, report_id: str) -> Optional[DiagnosticReport]:
        candidate = self._sample_dir / f"{report_id}.json"
        if candidate.exists():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                report = DiagnosticReport.from_fhir(payload)
                self._diagnostic_reports[report.id] = report
                return report
            except (OSError, json.JSONDecodeError, ValueError, ValidationError):
                return None

        for path in self._sample_dir.glob(f"{report_id}_fhir.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                report = DiagnosticReport.from_fhir(payload)
                self._diagnostic_reports[report.id] = report
                return report
            except (OSError, json.JSONDecodeError, ValueError, ValidationError):
                continue
        return None

    def _extract_resource_id(self, payload: Dict[str, Any], location: Optional[str]) -> str:
        if payload.get("id"):
            return payload["id"]
        if location:
            return location.rstrip("/").split("/")[-1]
        identifiers = payload.get("identifier")
        if isinstance(identifiers, list) and identifiers:
            candidate = identifiers[0]
            if isinstance(candidate, dict) and candidate.get("value"):
                return candidate["value"]
        generated = self._generate_order_id()
        LOGGER.debug(
            "Remote ServiceRequest response missing `id`; generated fallback.",
            extra={"context": {"generated": generated}},
        )
        return generated

    def _audit(self, action: str, fields: Optional[Dict[str, Any]] = None) -> None:
        context = {
            "action": action,
            "mode": "mock" if self.use_mock else "remote",
            "base_url": self.base_url,
        }
        if fields:
            context.update(fields)
        AUDIT_LOGGER.info("EHR interaction", extra={"context": context})

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass
