from __future__ import annotations

"""Utilities for loading, chunking, and indexing medical guideline content."""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.services.nim_embeddings import EmbeddingClient
from src.services.vector_store import VectorStore
from src.utils.logger import get_logger


@dataclass
class GuidelineChunk:
    """A structured slice of a guideline document suitable for retrieval."""

    chunk_id: str
    text: str
    source: str
    category: str
    size_min_mm: Optional[float]
    size_max_mm: Optional[float]
    risk_level: Optional[str]
    recommendation: str
    citation: str
    modality: Optional[str] = None


class GuidelineIndexer:
    """Convert guideline markdown into retrieval-ready document chunks."""

    SECTION_PATTERN = re.compile(r"^(##+)\s+(.*)$", re.MULTILINE)
    SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9])")
    SIZE_PATTERNS: Sequence[Tuple[re.Pattern[str], str]] = (
        (re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "range"),
        (re.compile(r"(?:≥|>=)\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "gte"),
        (re.compile(r"(?:≤|<=)\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "lte"),
        (re.compile(r"<\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "lt"),
        (re.compile(r">\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "gt"),
        (re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE), "single"),
    )
    MODALITY_KEYWORDS: Sequence[Tuple[re.Pattern[str], str]] = (
        (re.compile(r"\bpet[-/]?ct\b", re.IGNORECASE), "PET-CT"),
        (re.compile(r"\bpet\b", re.IGNORECASE), "PET"),
        (re.compile(r"\bmri\b", re.IGNORECASE), "MRI"),
        (re.compile(r"\bldct\b", re.IGNORECASE), "CT"),
        (re.compile(r"\bct\b", re.IGNORECASE), "CT"),
        (re.compile(r"\bultrasound\b", re.IGNORECASE), "Ultrasound"),
        (re.compile(r"\bceus\b", re.IGNORECASE), "CEUS"),
        (re.compile(r"\bbiopsy\b", re.IGNORECASE), "Biopsy"),
    )

    MIN_WORDS = 100
    TARGET_MIN_WORDS = 200
    TARGET_MAX_WORDS = 400
    MAX_WORDS = 500
    OPEN_ENDED_MAX = 999.0

    def __init__(self) -> None:
        self._logger = get_logger("audra.guidelines.indexer")

    # ------------------------------------------------------------------ #

    def load_guideline(self, file_path: str) -> Dict[str, str]:
        """Read a markdown guideline file and extract metadata."""

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Guideline file not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        title = ""
        citation = ""
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not title and stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                continue
            if not citation and "reference" in stripped.lower():
                citation = self._clean_reference(stripped)
            if title and citation:
                break

        if not title:
            title = path.stem.replace("_", " ").title()

        return {"title": title, "citation": citation, "content": content}

    def chunk_guideline(self, content: str, source_name: str) -> List[GuidelineChunk]:
        """Split guideline content into semantically coherent retrieval chunks."""

        sections = self._parse_sections(content)
        if not sections:
            sections = [{"title": "Overview", "level": 2, "body": content.strip()}]

        processed_sections: List[Dict[str, object]] = []
        for section in sections:
            body = str(section["body"]).strip()
            if not body:
                continue
            splits = self._split_large_section(body)
            for idx, part in enumerate(splits):
                part = part.strip()
                if not part:
                    continue
                title = str(section["title"])
                if len(splits) > 1:
                    title = f"{title} (part {idx + 1})"
                processed_sections.append(
                    {
                        "title": title,
                        "level": section["level"],
                        "body": part,
                        "word_count": self._word_count(part),
                    }
                )

        merged_sections = self._merge_small_sections(processed_sections)

        chunks: List[GuidelineChunk] = []
        for section in merged_sections:
            title = str(section["title"])
            body = str(section["body"]).strip()
            if not body:
                continue

            text = f"{title}\n\n{body}".strip()
            size_min, size_max = self._extract_size_range(text)
            risk_level = self._infer_risk_level(text)
            modality = self._infer_modality(text)

            chunk = GuidelineChunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                source=source_name,
                category=title,
                size_min_mm=size_min,
                size_max_mm=size_max,
                risk_level=risk_level,
                recommendation=body,
                citation="",
                modality=modality,
            )
            chunks.append(chunk)

        return chunks

    def index_all_guidelines(
        self,
        guidelines_dir: str,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
        *,
        batch_size: int = 50,
    ) -> None:
        """Load, chunk, embed, and index all markdown guidelines."""

        directory = Path(guidelines_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Guidelines directory not found: {guidelines_dir}")

        markdown_files = sorted(directory.glob("*.md"))
        if not markdown_files:
            self._logger.warning(
                "No guideline files discovered.",
                extra={"context": {"directory": str(directory)}},
            )
            return

        total_chunks = 0
        total_words = 0
        guideline_stats: List[Dict[str, object]] = []

        for file_path in markdown_files:
            metadata = self.load_guideline(str(file_path))
            title = metadata["title"]
            citation = metadata.get("citation", "")
            chunks = self.chunk_guideline(metadata["content"], title)
            for chunk in chunks:
                chunk.citation = citation

            if not chunks:
                self._logger.warning(
                    "No chunks created from guideline.",
                    extra={"context": {"file": str(file_path)}},
                )
                continue

            self._logger.info(f"Indexing {title}... {len(chunks)} chunks")

            texts = [chunk.text for chunk in chunks]
            embeddings = embedding_client.embed_batch(texts)

            documents = []
            for chunk, embedding in zip(chunks, embeddings):
                total_chunks += 1
                total_words += self._word_count(chunk.text)
                metadata_payload: Dict[str, object] = {
                    "source": chunk.source,
                    "category": chunk.category,
                    "citation": chunk.citation,
                    "recommendation": chunk.recommendation,
                }
                if chunk.size_min_mm is not None:
                    metadata_payload["size_min_mm"] = float(chunk.size_min_mm)
                if chunk.size_max_mm is not None:
                    metadata_payload["size_max_mm"] = float(chunk.size_max_mm)
                if chunk.risk_level:
                    metadata_payload["risk_level"] = chunk.risk_level
                if chunk.modality:
                    metadata_payload["modality"] = chunk.modality

                documents.append(
                    {
                        "id": chunk.chunk_id,
                        "text": chunk.text,
                        "embedding": embedding,
                        "metadata": metadata_payload,
                    }
                )

            vector_store.index_batch(documents, batch_size=batch_size)
            guideline_stats.append({"title": title, "chunks": len(chunks)})

        if total_chunks:
            avg_words = total_words / total_chunks
            summary_context = {
                "guidelines_indexed": len(guideline_stats),
                "chunks_indexed": total_chunks,
                "avg_chunk_words": round(avg_words, 1),
            }
            self._logger.info(
                "Guideline indexing complete.",
                extra={"context": summary_context},
            )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _parse_sections(self, content: str) -> List[Dict[str, object]]:
        matches = list(self.SECTION_PATTERN.finditer(content))
        sections: List[Dict[str, object]] = []

        if matches:
            prefix = content[: matches[0].start()].strip()
            if prefix:
                sections.append({"title": "Overview", "level": 2, "body": prefix})

            for idx, match in enumerate(matches):
                start = match.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
                body = content[start:end].strip()
                if not body:
                    continue
                heading_marks, title = match.groups()
                sections.append(
                    {
                        "title": title.strip(),
                        "level": len(heading_marks),
                        "body": body,
                    }
                )
        else:
            stripped = content.strip()
            if stripped:
                sections.append({"title": "Overview", "level": 2, "body": stripped})

        return sections

    def _split_large_section(self, body: str) -> List[str]:
        paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return [body]

        chunks: List[str] = []
        current: List[str] = []
        for paragraph in paragraphs:
            candidate = "\n\n".join([*current, paragraph]).strip()
            if current and self._word_count(candidate) > self.MAX_WORDS:
                chunks.append("\n\n".join(current).strip())
                current = [paragraph]
            else:
                current.append(paragraph)

        if current:
            chunks.append("\n\n".join(current).strip())

        # Further split any oversized chunk using sentence boundaries.
        normalized: List[str] = []
        for chunk in chunks:
            if self._word_count(chunk) <= self.MAX_WORDS:
                normalized.append(chunk)
                continue
            sentences = self.SENTENCE_SPLIT_PATTERN.split(chunk)
            sentence_buffer: List[str] = []
            for sentence in sentences:
                candidate = " ".join([*sentence_buffer, sentence]).strip()
                if sentence_buffer and self._word_count(candidate) > self.MAX_WORDS:
                    normalized.append(" ".join(sentence_buffer).strip())
                    sentence_buffer = [sentence]
                else:
                    sentence_buffer.append(sentence)
            if sentence_buffer:
                normalized.append(" ".join(sentence_buffer).strip())

        return [item for item in normalized if item]

    def _merge_small_sections(self, sections: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
        merged: List[Dict[str, object]] = []
        buffer: Optional[Dict[str, object]] = None

        for section in sections:
            word_count = int(section.get("word_count", self._word_count(str(section.get("body", "")))))

            if buffer is not None:
                buffer_word_count = self._word_count(str(buffer["body"]))
                if buffer_word_count < self.TARGET_MIN_WORDS:
                    buffer["body"] = f"{buffer['body']}\n\n{section['body']}".strip()
                    buffer["title"] = f"{buffer['title']} | {section['title']}"
                    buffer["word_count"] = self._word_count(str(buffer["body"]))
                    continue
                merged.append(buffer)
                buffer = None

            if word_count < self.MIN_WORDS:
                if buffer is None:
                    buffer = {
                        "title": section["title"],
                        "body": section["body"],
                        "word_count": word_count,
                    }
                else:
                    buffer["body"] = f"{buffer['body']}\n\n{section['body']}".strip()
                    buffer["title"] = f"{buffer['title']} | {section['title']}"
                    buffer["word_count"] = self._word_count(str(buffer["body"]))
                continue

            merged.append(
                {
                    "title": section["title"],
                    "body": section["body"],
                    "word_count": word_count,
                }
            )

        if buffer is not None:
            if merged:
                merged[-1]["body"] = f"{merged[-1]['body']}\n\n{buffer['body']}".strip()
                merged[-1]["title"] = f"{merged[-1]['title']} | {buffer['title']}"
                merged[-1]["word_count"] = self._word_count(str(merged[-1]["body"]))
            else:
                merged.append(buffer)

        return merged

    def _extract_size_range(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        for pattern, kind in self.SIZE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            if kind == "range":
                start, end = match.groups()
                return float(start), float(end)
            value = float(match.group(1))
            if kind in {"gte", "gt"}:
                return value, self.OPEN_ENDED_MAX
            if kind in {"lte", "lt"}:
                return 0.0, value
            if kind == "single":
                return value, value
        return None, None

    def _infer_risk_level(self, text: str) -> Optional[str]:
        lowered = text.lower()
        matches = []
        if "high risk" in lowered:
            matches.append("high")
        if "low risk" in lowered:
            matches.append("low")
        if "intermediate risk" in lowered:
            matches.append("intermediate")

        if not matches:
            return None
        if len(set(matches)) == 1:
            return matches[0]
        return "mixed"

    def _infer_modality(self, text: str) -> Optional[str]:
        for pattern, modality in self.MODALITY_KEYWORDS:
            if pattern.search(text):
                return modality
        return None

    @staticmethod
    def _word_count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _clean_reference(line: str) -> str:
        cleaned = re.sub(r"\*\*", "", line)
        cleaned = re.sub(r"^Reference[:\s-]*", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned
