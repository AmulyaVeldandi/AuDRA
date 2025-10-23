from __future__ import annotations

import base64
from typing import Dict, Iterable

import pytest

from src.parsers.fhir_parser import parse_diagnostic_report
from src.parsers.report_parser import parse_report


def _find_finding(findings: Iterable[Dict[str, object]], tag: str) -> Dict[str, object]:
    for finding in findings:
        tags = finding.get('tags', [])
        if isinstance(tags, list) and tag in tags:
            return finding
    raise AssertionError(f'No finding with tag "{tag}" found in {findings!r}')


def test_parse_report_detects_pulmonary_patterns() -> None:
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

    parsed = parse_report(report)

    assert parsed['study_context'].startswith('High-risk lung cancer screening.')
    assert parsed['impression'] == 'RUL 6 mm nodule with no suspicious change; likely inflammatory.'

    nodule = _find_finding(parsed['findings'], 'nodule')
    assert {'nodule', 'size:6mm', 'lobe:RUL', 'type:solid'}.issubset(set(nodule['tags']))  # type: ignore[index]
    assert nodule['confidence'] >= 0.75  # type: ignore[index]

    ggo = _find_finding(parsed['findings'], 'ggo')
    assert ggo['confidence'] >= 0.6  # type: ignore[index]

    consolidation = _find_finding(parsed['findings'], 'consolidation')
    assert consolidation['confidence'] >= 0.55  # type: ignore[index]


def test_parse_report_detects_liver_lesion_li_rads() -> None:
    report = (
        'Indication: Follow-up for hepatic adenomas.\n'
        'Findings:\n'
        'Segment VII hepatic lesion measures 2.1 cm and demonstrates arterial washout. '
        'LI-RADS 4 observation with capsular enhancement.\n'
        'Impression:\n'
        'Arterial enhancing lesion compatible with LI-RADS 4 observation.'
    )

    parsed = parse_report(report)

    liver = _find_finding(parsed['findings'], 'liver_lesion')
    assert 'li-rads:LR-4' in liver['tags']  # type: ignore[index]
    assert liver['confidence'] >= 0.7  # type: ignore[index]


def test_parse_diagnostic_report_combines_conclusion_and_presented_form() -> None:
    payload_text = (
        'FINDINGS:\n'
        '1. Right upper lobe pulmonary nodule as described above.\n'
        '2. No pleural effusion.\n'
    )
    data_url = (
        'data:text/plain;base64,'
        + base64.b64encode('Presented form narrative from SIIM sample.'.encode('utf-8')).decode('utf-8')
    )
    resource = {
        'resourceType': 'DiagnosticReport',
        'conclusion': 'SIIM CT Chest impression: Stable RUL nodule.',
        'presentedForm': [
            {
                'contentType': 'text/plain',
                'data': base64.b64encode(payload_text.encode('utf-8')).decode('utf-8'),
            },
            {
                'contentType': 'text/plain',
                'url': data_url,
            },
        ],
    }

    combined = parse_diagnostic_report(resource)
    assert 'SIIM CT Chest impression: Stable RUL nodule.' in combined
    assert 'Right upper lobe pulmonary nodule' in combined
    assert 'Presented form narrative from SIIM sample.' in combined
