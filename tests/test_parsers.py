from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from src.parsers.fhir_parser import FHIRParser
from src.parsers.report_parser import Finding, ReportParser, parse_report


def _select(findings: Iterable[Finding], predicate: Callable[[Finding], bool]) -> Finding:
    for finding in findings:
        if predicate(finding):
            return finding
    raise AssertionError("Expected finding not located.")


def test_parse_report_detects_pulmonary_patterns() -> None:
    parser = ReportParser()
    report = (
        'History: High-risk lung cancer screening.\n'
        'Technique: Thin-section chest CT with contrast.\n'
        'Findings:\n'
        'A 6 mm solid pulmonary nodule is present in the right upper lobe along the '
        'apical segment bronchus.\n'
        'Additional scattered ground-glass opacities are seen in the left lower lobe.\n'
        'Dense consolidation involves the lingula.\n'
        'Impression:\n'
        'RUL 6 mm nodule with no suspicious change; likely inflammatory.'
    )

    findings = parser.parse(report)
    assert all(isinstance(item, Finding) for item in findings)

    nodule = _select(findings, lambda item: item.finding_type == 'nodule')
    assert nodule.size_mm == 6.0
    assert nodule.location == 'RUL'
    assert 'solid' in nodule.characteristics
    assert nodule.confidence >= 0.9

    ggo = _select(findings, lambda item: 'ground-glass' in item.characteristics)
    assert ggo.location == 'LLL'
    assert ggo.confidence >= 0.6

    consolidation = _select(findings, lambda item: 'consolidation' in item.characteristics)
    assert consolidation.location == 'LINGULA'
    assert consolidation.confidence >= 0.6
    assert 'lingula' in consolidation.context.lower()

    via_helper = parse_report(report)
    assert all(isinstance(item, Finding) for item in via_helper)


def test_parse_report_detects_liver_lesion_li_rads() -> None:
    parser = ReportParser()
    report = (
        'Indication: Follow-up for hepatic adenomas.\n'
        'Findings:\n'
        'Segment VII hepatic lesion measures 2.1 cm and demonstrates arterial washout. '
        'LI-RADS 4 observation with capsular enhancement.\n'
        'Impression:\n'
        'Arterial enhancing lesion compatible with LI-RADS 4 observation.'
    )

    findings = parser.parse(report)

    lesion = _select(findings, lambda item: 'segment vii' in item.context.lower())
    assert lesion.location == 'Segment VII'
    assert lesion.size_mm == 21.0
    assert lesion.finding_type == 'lesion'
    assert lesion.confidence >= 0.78

    li_rads = _select(findings, lambda item: 'li-rads' in item.context.lower())
    assert li_rads.confidence >= 0.6


def test_extract_measurements_normalises_units() -> None:
    parser = ReportParser()
    text = 'Measurements include a 3mm nodule, a 2.5 cm mass, and a 1.2 x 0.8 cm lesion.'
    measurements = parser.extract_measurements(text)
    assert measurements == [(3.0, 'mm'), (25.0, 'mm'), (12.0, 'mm')]


def test_parse_diagnostic_report_combines_conclusion_and_presented_form() -> None:
    parser = FHIRParser()
    report_path = Path('data/sample_reports/chest_ct_ggo_fhir.json')
    report_data = json.loads(report_path.read_text(encoding='utf-8'))

    report_text, patient = parser.parse_diagnostic_report(report_data)

    assert 'Ground-glass opacities' in report_text
    assert patient['patient_id'] == 'patient-123'
    assert patient['gender'] == 'female'
    assert patient['mrn'] == 'MRN-44521'

    birth_date = datetime.fromisoformat('1980-05-12T00:00:00').date()
    today = datetime.now(timezone.utc).date()
    expected_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    assert patient['age'] == expected_age


def test_parse_diagnostic_report_falls_back_to_presented_form() -> None:
    parser = FHIRParser()
    payload_text = (
        'FINDINGS:\n'
        '1. Right upper lobe pulmonary nodule as described above.\n'
        '2. No pleural effusion.\n'
    )
    resource = {
        'resourceType': 'DiagnosticReport',
        'id': 'report-1',
        'status': 'final',
        'code': {'text': 'CT Chest', 'coding': [{'system': 'http://loinc.org', 'code': '71250-2'}]},
        'subject': {'reference': 'Patient/example'},
        'effectiveDateTime': '2024-01-01T00:00:00Z',
        'presentedForm': [
            {
                'contentType': 'text/plain',
                'data': base64.b64encode(payload_text.encode('utf-8')).decode('utf-8'),
            },
        ],
    }

    text, metadata = parser.parse_diagnostic_report(resource)
    assert text.startswith('FINDINGS:')
    assert metadata['patient_id'] == 'example'


def test_validate_diagnostic_report_detects_missing_fields() -> None:
    parser = FHIRParser()
    invalid_report = {
        'resourceType': 'DiagnosticReport',
        'status': 'final',
        'code': {'text': 'CT Chest'},
        'effectiveDateTime': '2024-01-01T00:00:00Z',
    }

    assert parser.validate_diagnostic_report(invalid_report) is False
