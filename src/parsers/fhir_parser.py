'''Parse FHIR DiagnosticReport resources.'''

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Dict, Iterable, List
from urllib.parse import unquote_to_bytes


def _decode_base64_payload(payload: str) -> str:
    '''Decode a base64 payload into UTF-8 text, ignoring undecodable bytes.'''
    try:
        decoded = base64.b64decode(payload, validate=False)
    except (ValueError, binascii.Error):
        return ''
    try:
        return decoded.decode('utf-8', errors='ignore').strip()
    except UnicodeDecodeError:
        return decoded.decode('utf-8', errors='ignore').strip()


def _extract_from_data_url(data_url: str) -> str:
    '''Extract and decode text from a data: URL attachment.'''
    match = re.match(r'^data:(?P<mime>[^;]+);(?P<encoding>[^,]+),(?P<payload>.+)$', data_url, re.IGNORECASE)
    if not match:
        return ''
    encoding = match.group('encoding').lower()
    payload = match.group('payload')
    if 'base64' in encoding:
        return _decode_base64_payload(payload)
    # Percent-encoded plain text
    try:
        return unquote_to_bytes(payload).decode('utf-8', errors='ignore').strip()
    except Exception:
        return ''


def _iter_presented_form_texts(resource: Dict[str, Any]) -> Iterable[str]:
    '''Yield textual payloads from DiagnosticReport.presentedForm attachments.'''
    attachments = resource.get('presentedForm') or []
    if not isinstance(attachments, list):
        return []

    results: List[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        # Prioritize explicit textual content when present
        text_value = attachment.get('text') or attachment.get('title')
        if isinstance(text_value, str) and text_value.strip():
            results.append(text_value.strip())
            continue

        data = attachment.get('data')
        if isinstance(data, str) and data.strip():
            decoded = _decode_base64_payload(data.strip())
            if decoded:
                results.append(decoded)
                continue

        url = attachment.get('url')
        if isinstance(url, str) and url.startswith('data:'):
            decoded = _extract_from_data_url(url)
            if decoded:
                results.append(decoded)
                continue

        # Fallback for inline binary content represented as bytes
        data_bytes = attachment.get('dataBytes')
        if isinstance(data_bytes, (bytes, bytearray)):
            try:
                results.append(bytes(data_bytes).decode('utf-8', errors='ignore').strip())
            except Exception:
                continue

    return [text for text in results if text]


def parse_diagnostic_report(resource: Dict[str, Any]) -> str:
    '''
    Collect the textual narrative of a FHIR DiagnosticReport.

    The DiagnosticReport.conclusion field is merged with any textual payloads found
    in DiagnosticReport.presentedForm attachments. The combined string is separated
    by blank lines to maintain readability.
    '''
    if not isinstance(resource, dict):
        return ''

    pieces: List[str] = []

    conclusion = resource.get('conclusion')
    if isinstance(conclusion, str) and conclusion.strip():
        pieces.append(conclusion.strip())

    for attachment_text in _iter_presented_form_texts(resource):
        if attachment_text:
            pieces.append(attachment_text)

    return '\n\n'.join(pieces)
