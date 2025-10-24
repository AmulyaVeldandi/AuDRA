from __future__ import annotations

"""Extraction utilities for structuring narrative radiology reports."""

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

# --------------------------------------------------------------------------- #
# Section parsing utilities
# --------------------------------------------------------------------------- #

SECTION_HEADER_PATTERN = re.compile(
    r"(?im)^(?P<header>[A-Za-z][A-Za-z0-9 /\\-]{1,60})\s*:\s*(?P<inline>.*)$"
)

SECTION_ALIASES: Dict[str, Iterable[str]] = {
    "findings": {"findings", "finding", "results", "observations"},
    "impression": {"impression", "impressions", "conclusion", "assessment", "summary"},
}

# --------------------------------------------------------------------------- #
# Extraction patterns
# --------------------------------------------------------------------------- #

SIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|millimeters?|cm|centimeters?)", re.IGNORECASE)
SIZE_COMPOSITE_PATTERN = re.compile(
    r"(?P<first>\d+(?:\.\d+)?)\s*(?:x|×|\u00d7)\s*(?P<second>\d+(?:\.\d+)?)\s*(?P<unit>mm|millimeters?|cm|centimeters?)",
    re.IGNORECASE,
)

LUNG_LOCATION_PATTERNS: Dict[re.Pattern[str], str] = {
    re.compile(r"\bright upp(?:er)? lobe\b", re.IGNORECASE): "RUL",
    re.compile(r"\bright mid(?:dle)? lobe\b", re.IGNORECASE): "RML",
    re.compile(r"\bright low(?:er)? lobe\b", re.IGNORECASE): "RLL",
    re.compile(r"\bleft upp(?:er)? lobe\b", re.IGNORECASE): "LUL",
    re.compile(r"\bleft low(?:er)? lobe\b", re.IGNORECASE): "LLL",
    re.compile(r"\blingula\b", re.IGNORECASE): "LINGULA",
    re.compile(r"\brul\b", re.IGNORECASE): "RUL",
    re.compile(r"\brml\b", re.IGNORECASE): "RML",
    re.compile(r"\brll\b", re.IGNORECASE): "RLL",
    re.compile(r"\blul\b", re.IGNORECASE): "LUL",
    re.compile(r"\blll\b", re.IGNORECASE): "LLL",
}

LIVER_SEGMENT_PATTERN = re.compile(r"\bsegment\s+(?P<segment>(?:[ivx]+|\d+))\b", re.IGNORECASE)
BRAIN_LOCATION_PATTERN = re.compile(
    r"\b(frontal|parietal|temporal|occipital|cerebellar|brainstem|basal ganglia|thalamus)\b", re.IGNORECASE
)

CHARACTERISTIC_PATTERNS: Dict[re.Pattern[str], str] = {
    re.compile(r"\bground[-\s]?glass\b", re.IGNORECASE): "ground-glass",
    re.compile(r"\bpart[-\s]?solid\b", re.IGNORECASE): "part-solid",
    re.compile(r"\bsolid\b", re.IGNORECASE): "solid",
    re.compile(r"\bsubsolid\b", re.IGNORECASE): "subsolid",
    re.compile(r"\bspiculated\b", re.IGNORECASE): "spiculated",
    re.compile(r"\bsmooth\b", re.IGNORECASE): "smooth",
    re.compile(r"\bcalcified\b", re.IGNORECASE): "calcified",
    re.compile(r"\birregular\b", re.IGNORECASE): "irregular",
    re.compile(r"\blobulated\b", re.IGNORECASE): "lobulated",
    re.compile(r"\bconsolidation\b", re.IGNORECASE): "consolidation",
}

FINDING_KEYWORDS = re.compile(
    r"\b(nodule|mass|lesion|opacity|ground[-\s]?glass|consolidation|adenopathy|cyst|tumou?r|metastasis)\b",
    re.IGNORECASE,
)

UNCERTAINTY_PATTERN = re.compile(
    r"\b(possible|possibly|probable|probably|suggests?|may represent|cannot exclude|indeterminate)\b",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    finding_id: str
    finding_type: str
    size_mm: Optional[float] = None
    location: str = ""
    characteristics: List[str] = field(default_factory=list)
    context: str = ""
    confidence: float = 0.0


# --------------------------------------------------------------------------- #
# Parser implementation
# --------------------------------------------------------------------------- #


class ReportParser:
    """Structured finding extractor for narrative radiology reports."""

    def parse(self, report_text: str) -> List[Finding]:
        """Return structured findings extracted from the supplied report."""

        if not isinstance(report_text, str):
            return []

        normalized = report_text.replace("\r\n", "\n").strip()
        if not normalized:
            return []

        sections = _split_sections(normalized)
        candidate_blocks: List[str] = []
        for key in ("findings", "impression"):
            candidate_blocks.extend(sections.get(key, []))
        if not candidate_blocks:
            candidate_blocks = [normalized]

        findings: List[Finding] = []
        seen_snippets: set[str] = set()
        for block in candidate_blocks:
            for snippet in self._split_into_statements(block):
                key = snippet.lower()
                if key in seen_snippets:
                    continue
                if not self._looks_like_finding(snippet):
                    continue
                finding = self._build_finding(snippet)
                if finding is None:
                    continue
                seen_snippets.add(key)
                findings.append(finding)
        return findings

    def extract_measurements(self, text: str) -> List[Tuple[float, str]]:
        """Extract size measurements from the text, normalised to millimetres."""

        measurements_with_pos: List[Tuple[int, float]] = []
        consumed_spans: List[Tuple[int, int]] = []

        for match in SIZE_COMPOSITE_PATTERN.finditer(text):
            first = float(match.group("first"))
            second = float(match.group("second"))
            unit = match.group("unit")
            values_mm = [self._to_mm(first, unit), self._to_mm(second, unit)]
            measurements_with_pos.append((match.start(), round(max(values_mm), 1)))
            consumed_spans.append(match.span())

        for match in SIZE_PATTERN.finditer(text):
            span = match.span()
            if any(start <= span[0] < end for start, end in consumed_spans):
                continue
            value = float(match.group(1))
            unit = match.group(2)
            measurements_with_pos.append((match.start(), round(self._to_mm(value, unit), 1)))

        measurements_with_pos.sort(key=lambda item: item[0])
        return [(value, "mm") for _, value in measurements_with_pos]

    def extract_locations(self, text: str) -> List[str]:
        """Return normalised anatomical location labels."""

        locations: List[str] = []
        for pattern, label in LUNG_LOCATION_PATTERNS.items():
            if pattern.search(text):
                locations.append(label)

        for match in LIVER_SEGMENT_PATTERN.finditer(text):
            segment = match.group("segment").upper()
            normalised = self._normalise_liver_segment(segment)
            if normalised:
                locations.append(f"Segment {normalised}")

        for match in BRAIN_LOCATION_PATTERN.finditer(text):
            locations.append(match.group(1).strip().title())

        seen: set[str] = set()
        unique_locations: List[str] = []
        for location in locations:
            if location not in seen:
                seen.add(location)
                unique_locations.append(location)
        return unique_locations

    def extract_characteristics(self, text: str) -> List[str]:
        """Return descriptive characteristics mentioned in the text."""

        characteristics: List[str] = []
        for pattern, label in CHARACTERISTIC_PATTERNS.items():
            if pattern.search(text):
                characteristics.append(label)
        seen: set[str] = set()
        unique: List[str] = []
        for characteristic in characteristics:
            if characteristic not in seen:
                seen.add(characteristic)
                unique.append(characteristic)
        return unique

    def classify_finding_type(self, text: str, characteristics: List[str]) -> str:
        """Infer the finding type using rules and extracted metadata."""

        text_lower = text.lower()
        measurements = self.extract_measurements(text)
        size_mm = measurements[0][0] if measurements else None
        locations = self.extract_locations(text)

        if "ground-glass" in characteristics or "opacity" in text_lower:
            return "opacity"
        if "consolidation" in characteristics:
            return "opacity"
        if size_mm is not None and size_mm >= 30:
            return "mass"
        if "mass" in text_lower:
            return "mass"
        lung_locations = {"RUL", "RML", "RLL", "LUL", "LLL", "LINGULA"}
        if locations and any(loc in lung_locations for loc in locations):
            if size_mm is None or size_mm < 30 or "nodule" in text_lower:
                return "nodule"
        if "nodule" in text_lower and (size_mm is None or size_mm < 30):
            return "nodule"
        if "lesion" in text_lower:
            return "lesion"
        return "lesion"

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_finding(self, snippet: str) -> Optional[Finding]:
        measurements = self.extract_measurements(snippet)
        size_mm = measurements[0][0] if measurements else None
        locations = self.extract_locations(snippet)
        characteristics = self.extract_characteristics(snippet)
        finding_type = self.classify_finding_type(snippet, characteristics)
        location_display = locations[0] if locations else ""
        confidence = self._score_confidence(
            snippet,
            finding_type,
            size_mm,
            bool(location_display),
            characteristics,
        )

        return Finding(
            finding_id=uuid4().hex,
            finding_type=finding_type,
            size_mm=size_mm,
            location=location_display,
            characteristics=characteristics,
            context=snippet.strip(),
            confidence=confidence,
        )

    def _split_into_statements(self, block: str) -> List[str]:
        statements: List[str] = []
        for raw_line in block.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            stripped = re.sub(r"^\d+[\.\)]\s*", "", stripped)
            stripped = stripped.lstrip("-•*").strip()
            if not stripped:
                continue
            parts = re.split(r"(?<=[.])\s+(?=[A-Z])", stripped)
            for part in parts:
                candidate = part.strip()
                if candidate:
                    statements.append(candidate)
        return statements

    def _looks_like_finding(self, text: str) -> bool:
        if len(text) < 12:
            return False
        if FINDING_KEYWORDS.search(text):
            return True
        return bool(self.extract_measurements(text))

    def _score_confidence(
        self,
        snippet: str,
        finding_type: str,
        size_mm: Optional[float],
        has_location: bool,
        characteristics: List[str],
    ) -> float:
        detail_score = 0
        if size_mm is not None:
            detail_score += 1
        if has_location:
            detail_score += 1
        if finding_type:
            detail_score += 1
        if characteristics:
            detail_score += 1

        if detail_score >= 3:
            confidence = 0.92
        elif detail_score == 2:
            confidence = 0.78
        elif detail_score == 1:
            confidence = 0.62
        else:
            confidence = 0.5

        if UNCERTAINTY_PATTERN.search(snippet):
            confidence = max(0.4, confidence - 0.2)

        return round(min(confidence, 0.99), 2)

    def _to_mm(self, value: float, unit: str) -> float:
        unit_lower = unit.lower()
        if unit_lower.startswith("cm"):
            return value * 10.0
        return value

    def _normalise_liver_segment(self, token: str) -> Optional[str]:
        roman_map = {
            "I": "I",
            "II": "II",
            "III": "III",
            "IV": "IV",
            "V": "V",
            "VI": "VI",
            "VII": "VII",
            "VIII": "VIII",
        }
        token_clean = token.upper()
        if token_clean in roman_map:
            return roman_map[token_clean]
        try:
            value = int(token_clean)
        except ValueError:
            return None
        if 1 <= value <= 8:
            return ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"][value - 1]
        return None


# --------------------------------------------------------------------------- #
# Convenience wrapper
# --------------------------------------------------------------------------- #


def parse_report(report_text: str) -> List[Finding]:
    """Convenience wrapper returning findings using the default parser."""

    parser = ReportParser()
    return parser.parse(report_text)


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _normalize_header(raw_header: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", raw_header.lower()).strip()
    for canonical, synonyms in SECTION_ALIASES.items():
        if cleaned in synonyms:
            return canonical
    return cleaned


def _split_sections(report: str) -> Dict[str, List[str]]:
    matches = list(SECTION_HEADER_PATTERN.finditer(report))
    if not matches:
        return {}

    sections: Dict[str, List[str]] = {}
    for idx, match in enumerate(matches):
        header = match.group("header").strip()
        inline = match.group("inline")
        content_start = match.start("inline") if inline else match.end()
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(report)
        content = report[content_start:next_start].strip()
        if not content:
            continue
        canonical = _normalize_header(header)
        sections.setdefault(canonical, []).append(content)
    return sections
