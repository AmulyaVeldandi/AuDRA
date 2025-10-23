'''Extract structured findings from free-text radiology reports.'''

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SECTION_HEADER_PATTERN = re.compile(
    r'(?im)^(?P<header>[A-Za-z][A-Za-z0-9 /\\-]{1,60})\s*:\s*(?P<inline>.*)$'
)

SECTION_ALIASES = {
    'history': {
        'history',
        'clinical history',
        'medical history',
        'past history',
        'previous history',
    },
    'indication': {
        'indication',
        'clinical indication',
        'reason for exam',
        'reason for study',
        'reason for examination',
        'reason for imaging',
        'exam indication',
    },
    'comparison': {'comparison', 'comparisons'},
    'technique': {'technique', 'exam technique'},
    'findings': {
        'findings',
        'finding',
        'findings and impression',
        'findings & impression',
        'results',
        'observations',
    },
    'impression': {
        'impression',
        'impressions',
        'conclusion',
        'conclusions',
        'assessment',
        'opinion',
        'summary',
    },
}

NODULE_PATTERN = re.compile(r'\b(?:pulmonary\s+)?nodules?\b', re.IGNORECASE)
SIZE_COMPOSITE_PATTERN = re.compile(
    r'(?P<first>\d+(?:\.\d+)?)\s*(?:x|×|\u00d7)\s*(?P<second>\d+(?:\.\d+)?)\s*(?P<unit>mm|millimeters?|cm|centimeters?)',
    re.IGNORECASE,
)
SIZE_PATTERN = re.compile(
    r'(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>mm|millimeters?|cm|centimeters?)', re.IGNORECASE
)
LOBE_PATTERNS = {
    re.compile(r'\bright upper lobe\b', re.IGNORECASE): 'RUL',
    re.compile(r'\bright middle lobe\b', re.IGNORECASE): 'RML',
    re.compile(r'\bright lower lobe\b', re.IGNORECASE): 'RLL',
    re.compile(r'\bleft upper lobe\b', re.IGNORECASE): 'LUL',
    re.compile(r'\bleft lower lobe\b', re.IGNORECASE): 'LLL',
    re.compile(r'\blingula\b', re.IGNORECASE): 'LINGULA',
    re.compile(r'\brul\b', re.IGNORECASE): 'RUL',
    re.compile(r'\brml\b', re.IGNORECASE): 'RML',
    re.compile(r'\brll\b', re.IGNORECASE): 'RLL',
    re.compile(r'\blul\b', re.IGNORECASE): 'LUL',
    re.compile(r'\blll\b', re.IGNORECASE): 'LLL',
}
NODULE_TYPE_PATTERNS = {
    re.compile(r'\bsolid\b', re.IGNORECASE): 'solid',
    re.compile(r'\bsubsolid\b', re.IGNORECASE): 'subsolid',
    re.compile(r'\bpart(?:ial)?[-\s]?solid\b', re.IGNORECASE): 'part-solid',
    re.compile(r'\bground[-\s]?glass\b', re.IGNORECASE): 'ground-glass',
}
GGO_PATTERN = re.compile(
    r'\b(?:ground[-\s]?glass(?:\s+opacit(?:y|ies))?|ggo(?:s)?)\b', re.IGNORECASE
)
CONSOLIDATION_PATTERN = re.compile(r'\bconsolidation(?:s)?\b', re.IGNORECASE)
LIRADS_PATTERN = re.compile(
    r'\b(?:li-?rads\s*(?P<li>[0-9m]{1,2})|lr-?(?P<lr>[0-9m]{1,2}))\b', re.IGNORECASE
)


def _normalize_header(raw_header: str) -> str:
    cleaned = re.sub(r'[^a-z0-9]+', ' ', raw_header.lower()).strip()
    for canonical, synonyms in SECTION_ALIASES.items():
        if cleaned in synonyms:
            return canonical
    return cleaned


def _split_sections(report: str) -> Dict[str, List[Dict[str, Any]]]:
    matches = list(SECTION_HEADER_PATTERN.finditer(report))
    sections: Dict[str, List[Dict[str, Any]]] = {}
    for idx, match in enumerate(matches):
        header = match.group('header').strip()
        inline = match.group('inline')
        if inline:
            content_start = match.start('inline')
        else:
            content_start = match.end()
            if content_start < len(report) and report[content_start] == '\n':
                content_start += 1
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(report)
        content = report[content_start:next_start].rstrip()
        canonical = _normalize_header(header)
        sections.setdefault(canonical, []).append(
            {
                'header': header,
                'text': content.strip(),
                'start': content_start,
                'end': next_start,
            }
        )
    return sections


def _line_span(text: str, position: int) -> Tuple[int, int]:
    start = text.rfind('\n', 0, position)
    if start == -1:
        start = 0
    else:
        start += 1
    end = text.find('\n', position)
    if end == -1:
        end = len(text)
    return start, end


def _format_size(size_mm: float) -> str:
    rounded = round(size_mm, 1)
    if math.isclose(rounded, round(rounded, 0)):
        rounded = round(rounded)
    return f'size:{int(rounded)}mm' if isinstance(rounded, int) else f'size:{rounded}mm'


def _extract_size_tag(snippet: str) -> Optional[str]:
    sizes: List[float] = []
    for match in SIZE_COMPOSITE_PATTERN.finditer(snippet):
        unit = match.group('unit').lower()
        values = [float(match.group('first')), float(match.group('second'))]
        factor = 10.0 if unit.startswith('cm') else 1.0
        sizes.extend(value * factor for value in values)
    for match in SIZE_PATTERN.finditer(snippet):
        unit = match.group('unit').lower()
        value = float(match.group('size'))
        factor = 10.0 if unit.startswith('cm') else 1.0
        sizes.append(value * factor)
    if not sizes:
        return None
    largest = max(sizes)
    if largest <= 0:
        return None
    return _format_size(largest)


def _extract_lobe_tag(snippet: str) -> Optional[str]:
    for pattern, label in LOBE_PATTERNS.items():
        if pattern.search(snippet):
            return f'lobe:{label}'
    return None


def _extract_nodule_type(snippet: str) -> Optional[str]:
    for pattern, label in NODULE_TYPE_PATTERNS.items():
        if pattern.search(snippet):
            return f'type:{label}'
    return None


def _deduplicate(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for finding in findings:
        span = tuple(finding.get('span', ()))  # type: ignore[arg-type]
        tags = tuple(sorted(finding.get('tags', ())))
        key = (span, tags)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _build_finding(
    text: str,
    span_start: int,
    span_end: int,
    tags: Iterable[str],
    confidence: float,
) -> Dict[str, Any]:
    snippet = text[span_start:span_end].strip()
    return {
        'span': (span_start, span_end),
        'text': snippet,
        'tags': list(tags),
        'confidence': round(max(0.0, min(confidence, 1.0)), 2),
    }


def _detect_pulmonary_nodules(report: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for match in NODULE_PATTERN.finditer(report):
        span_start, span_end = _line_span(report, match.start())
        snippet = report[span_start:span_end]
        tags = ['nodule']
        confidence = 0.65

        size_tag = _extract_size_tag(snippet)
        if size_tag:
            tags.append(size_tag)
            confidence += 0.1

        lobe_tag = _extract_lobe_tag(snippet)
        if lobe_tag:
            tags.append(lobe_tag)
            confidence += 0.1

        type_tag = _extract_nodule_type(snippet)
        if type_tag:
            tags.append(type_tag)
            confidence += 0.1

        findings.append(_build_finding(report, span_start, span_end, tags, confidence))
    return findings


def _detect_ground_glass(report: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for match in GGO_PATTERN.finditer(report):
        span_start, span_end = _line_span(report, match.start())
        findings.append(
            _build_finding(report, span_start, span_end, ['ggo'], confidence=0.6)
        )
    return findings


def _detect_consolidation(report: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for match in CONSOLIDATION_PATTERN.finditer(report):
        span_start, span_end = _line_span(report, match.start())
        findings.append(
            _build_finding(
                report, span_start, span_end, ['consolidation'], confidence=0.55
            )
        )
    return findings


def _detect_liver_lesions(report: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for match in LIRADS_PATTERN.finditer(report):
        span_start, span_end = _line_span(report, match.start())
        snippet = report[span_start:span_end]
        category = match.group('lr') or match.group('li') or ''
        category = category.upper()
        category_tag = f'li-rads:LR-{category}' if category else 'li-rads'
        tags = ['liver_lesion', category_tag]
        if re.search(r'\blesion\b', snippet, re.IGNORECASE):
            confidence = 0.8
        else:
            confidence = 0.7
        findings.append(_build_finding(report, span_start, span_end, tags, confidence))
    return findings


def _assemble_study_context(report: str, sections: Dict[str, List[Dict[str, Any]]]) -> str:
    context_parts: List[str] = []
    for key in ('history', 'indication', 'comparison'):
        entries = sections.get(key, [])
        for entry in entries:
            if entry['text']:
                context_parts.append(entry['text'])
                break
    if context_parts:
        return '\n'.join(context_parts).strip()

    first_section_start: Optional[int] = None
    for entries in sections.values():
        for entry in entries:
            if first_section_start is None or entry['start'] < first_section_start:
                first_section_start = entry['start']
    if first_section_start is not None and first_section_start > 0:
        preamble = report[:first_section_start].strip()
        if preamble:
            return preamble
    return ''


def _extract_impression(sections: Dict[str, List[Dict[str, Any]]]) -> str:
    for key in ('impression', 'conclusion', 'summary'):
        entries = sections.get(key, [])
        for entry in entries:
            if entry['text']:
                return entry['text']
    return ''


def _run_heuristic_extractors(report: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for extractor in (
        _detect_pulmonary_nodules,
        _detect_ground_glass,
        _detect_consolidation,
        _detect_liver_lesions,
    ):
        findings.extend(extractor(report))
    deduped = _deduplicate(findings)
    deduped.sort(key=lambda item: item['span'][0])
    return deduped


def parse_report(report_text: str) -> Dict[str, Any]:
    '''
    Parse a free-text radiology report into structured findings.

    Returns a dictionary composed of the detected study context, impression, and a
    list of heuristic findings with tagged metadata.
    '''
    if not isinstance(report_text, str):
        return {'study_context': '', 'impression': '', 'findings': []}

    normalized = report_text.replace('\r\n', '\n')
    sections = _split_sections(normalized)
    study_context = _assemble_study_context(normalized, sections)
    impression = _extract_impression(sections)
    findings = _run_heuristic_extractors(normalized)

    return {
        'study_context': study_context,
        'impression': impression,
        'findings': findings,
    }
