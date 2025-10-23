"""Parsing utilities for FHIR R4 DiagnosticReport resources."""

from __future__ import annotations

import base64
import binascii
import io
import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import unquote_to_bytes

from pydantic import ValidationError

from src.parsers.fhir_models import Attachment, DiagnosticReport, Patient
from src.utils.logger import get_logger

try:  # pragma: no cover - optional dependency
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

try:  # pragma: no cover - optional dependency
    import PyPDF2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    PyPDF2 = None

LOGGER = get_logger(__name__)


PatientMetadata = Dict[str, Optional[Union[str, int]]]


class FHIRParser:
    """Parser for DiagnosticReport resources using the local FHIR models."""

    def parse_diagnostic_report(self, fhir_json: Dict) -> Tuple[str, PatientMetadata]:
        """Extract the report text and patient metadata from a DiagnosticReport.

        The diagnostic narrative is derived from the `conclusion` field if present.
        Otherwise we fall back to decoding the first textual attachment in
        `presentedForm`. PDF attachments are decoded using pdfplumber or PyPDF2
        when available.
        """

        LOGGER.debug("Parsing DiagnosticReport resource.", extra={"context": {"id": fhir_json.get("id")}})

        if not self.validate_diagnostic_report(fhir_json):
            raise ValueError("Invalid DiagnosticReport resource.")

        try:
            report = DiagnosticReport.from_fhir(fhir_json)
        except (ValueError, ValidationError) as exc:
            LOGGER.error(
                "Failed to parse DiagnosticReport payload.",
                extra={"context": {"error": str(exc), "id": fhir_json.get("id")}},
            )
            raise

        report_text = self._extract_report_text(report)
        if not report_text:
            LOGGER.error(
                "DiagnosticReport is missing narrative content.",
                extra={"context": {"id": report.id}},
            )
            raise ValueError("DiagnosticReport must contain conclusion or textual attachment data.")

        patient_metadata = self.extract_patient_context(
            report.subject.reference,
            bundle=fhir_json,
        )

        return report_text, patient_metadata

    def extract_patient_context(self, patient_reference: str, bundle: Optional[Dict] = None) -> PatientMetadata:
        """Return patient metadata from a reference string and optional bundle."""

        patient_id = (patient_reference or "").split("/")[-1].strip()
        metadata: PatientMetadata = {
            "patient_id": patient_id or None,
            "age": None,
            "gender": None,
            "mrn": None,
        }

        if not bundle:
            return metadata

        patient_resource = self._locate_patient_resource(bundle, patient_id)
        if not patient_resource:
            LOGGER.debug(
                "Patient resource not found in bundle.",
                extra={"context": {"patient_id": patient_id}},
            )
            return metadata

        try:
            patient = Patient.from_fhir(patient_resource)
        except (ValueError, ValidationError) as exc:
            LOGGER.error(
                "Failed to parse contained Patient resource.",
                extra={"context": {"patient_id": patient_id, "error": str(exc)}},
            )
            return metadata

        metadata["gender"] = patient.gender
        metadata["mrn"] = self._extract_mrn(patient)
        metadata["age"] = self._calculate_age(patient.birthDate)
        return metadata

    def validate_diagnostic_report(self, fhir_json: Dict) -> bool:
        """Validate required DiagnosticReport fields and log issues."""

        try:
            report = DiagnosticReport.from_fhir(fhir_json)
        except (ValueError, ValidationError) as exc:
            LOGGER.error(
                "DiagnosticReport validation error.",
                extra={"context": {"error": str(exc), "resourceType": fhir_json.get("resourceType")}},
            )
            return False

        missing: List[str] = []
        if not report.id:
            missing.append("id")
        if not report.status:
            missing.append("status")
        if not report.code or not (report.code.text or report.code.coding):
            missing.append("code")
        if not report.subject or not report.subject.reference:
            missing.append("subject")

        if missing:
            LOGGER.error(
                "DiagnosticReport missing required fields.",
                extra={"context": {"id": report.id, "missing": missing}},
            )
            return False

        return True

    def _extract_report_text(self, report: DiagnosticReport) -> str:
        """Extract narrative text from conclusion or presentedForm attachments."""

        if report.conclusion and report.conclusion.strip():
            return report.conclusion.strip()

        attachments = report.presentedForm or []
        for attachment in attachments:
            text = self._decode_attachment(attachment)
            if text:
                return text

        return ""

    def _decode_attachment(self, attachment: Attachment) -> Optional[str]:
        """Decode a textual or PDF attachment into plain text."""

        if attachment.data:
            text = self._decode_base64_payload(attachment.data, attachment.contentType)
            if text:
                return text

        if attachment.url and attachment.url.startswith("data:"):
            text = self._decode_data_url(attachment.url)
            if text:
                return text

        if attachment.title and attachment.contentType and attachment.contentType.startswith("text/"):
            return attachment.title.strip()

        return None

    def _decode_base64_payload(self, payload: str, content_type: Optional[str]) -> Optional[str]:
        """Decode a base64 payload, handling text and PDF content types."""

        try:
            decoded = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error) as exc:
            LOGGER.warning(
                "Attachment payload is not valid base64; returning raw text.",
                extra={"context": {"error": str(exc)}},
            )
            return payload.strip()

        if content_type and "pdf" in content_type.lower():
            return self._extract_pdf_text(decoded)

        try:
            return decoded.decode("utf-8").strip()
        except UnicodeDecodeError:
            return decoded.decode("utf-8", errors="ignore").strip()

    def _decode_data_url(self, url: str) -> Optional[str]:
        """Decode a data URL containing base64 or percent-encoded text."""

        match = re.match(r"^data:(?P<mime>[^;]+);(?P<encoding>[^,]+),(?P<payload>.+)$", url, re.IGNORECASE)
        if not match:
            return None
        encoding = match.group("encoding").lower()
        payload = match.group("payload")
        if "base64" in encoding:
            return self._decode_base64_payload(payload, match.group("mime"))
        try:
            return unquote_to_bytes(payload).decode("utf-8").strip()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to decode data URL payload.", extra={"context": {"error": str(exc)}})
            return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from a PDF byte stream using pdfplumber or PyPDF2."""

        if pdfplumber:
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(filter(None, pages)).strip()
                if text:
                    return text
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.error("Failed to extract text using pdfplumber.", extra={"context": {"error": str(exc)}})

        if PyPDF2:
            try:
                reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                pages = [page.extract_text() or "" for page in reader.pages]
                text = "\n".join(filter(None, pages)).strip()
                if text:
                    return text
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.error("Failed to extract text using PyPDF2.", extra={"context": {"error": str(exc)}})

        LOGGER.warning("PDF attachment present but no PDF extraction library is available.")
        return None

    def _locate_patient_resource(self, bundle: Dict, patient_id: str) -> Optional[Dict]:
        """Search for a Patient resource within a bundle or contained resources."""

        if "entry" in bundle:
            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if (
                    isinstance(resource, dict)
                    and resource.get("resourceType") == "Patient"
                    and resource.get("id") == patient_id
                ):
                    return resource

        if "contained" in bundle:
            for resource in bundle.get("contained", []):
                if (
                    isinstance(resource, dict)
                    and resource.get("resourceType") == "Patient"
                    and resource.get("id") == patient_id
                ):
                    return resource

        return None

    def _extract_mrn(self, patient: Patient) -> Optional[str]:
        """Return an MRN value from the patient's identifiers if available."""

        for identifier in patient.identifier:
            system = (identifier.system or "").lower()
            if "mrn" in system or not system:
                return identifier.value
        return patient.identifier[0].value if patient.identifier else None

    def _calculate_age(self, birth_date: date) -> Optional[int]:
        """Compute patient age in years."""

        today = datetime.now(timezone.utc).date()
        years = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            years -= 1
        return years
