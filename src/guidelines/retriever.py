from __future__ import annotations

"""Guideline retrieval logic built on top of the vector store."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.guidelines.indexer import GuidelineChunk
from src.services.nim_embeddings import EmbeddingClient
from src.services.vector_store import VectorStore
from src.utils.logger import get_logger


@dataclass
class RetrievedDocument:
    """Internal wrapper for vector store hits."""

    id: str
    text: str
    score: float
    metadata: Dict[str, object]


class GuidelineRetriever:
    """Surface guideline chunks that align with radiology findings."""

    def __init__(self, embedding_client: EmbeddingClient, vector_store: VectorStore) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._logger = get_logger("audra.guidelines.retriever")

    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        finding: Dict[str, object],
        top_k: int = 5,
        use_filters: bool = True,
    ) -> List[GuidelineChunk]:
        """Return the top-k guideline chunks relevant to a clinical finding."""

        if top_k <= 0:
            raise ValueError("top_k must be positive.")

        query_text = self.build_query_text(finding)
        query_embedding = self._embedding_client.embed_text(query_text, prefix="query: ")

        filters = self._build_filters(finding) if use_filters else {}
        allowed_sources = filters.pop("sources", None) if filters else None

        self._logger.info(
            "Searching guideline corpus.",
            extra={
                "context": {
                    "query": query_text,
                    "filters": filters or None,
                    "top_k": top_k,
                }
            },
        )

        search_top_k = max(top_k * 3, 15)
        if filters:
            raw_hits = self._vector_store.search(
                query_embedding,
                top_k=search_top_k,
                filters=filters,
            )
        else:
            raw_hits = self._vector_store.hybrid_search(
                query_embedding,
                query_text,
                top_k=search_top_k,
            )

        documents = [
            RetrievedDocument(
                id=hit.get("id", ""),
                text=hit.get("text", "") or "",
                score=float(hit.get("score") or 0.0),
                metadata=hit.get("metadata", {}) or {},
            )
            for hit in raw_hits
        ]

        if allowed_sources:
            allowed = {source.lower() for source in allowed_sources}
            documents = [
                doc
                for doc in documents
                if doc.metadata.get("source", "").lower() in allowed
            ]

        reranked = self.rerank_results(documents, finding)
        top_results = reranked[:top_k]

        if top_results:
            top_doc = top_results[0]
            self._logger.info(
                "Top guideline match identified.",
                extra={
                    "context": {
                        "source": top_doc.metadata.get("source"),
                        "category": top_doc.metadata.get("category"),
                        "score": top_doc.score,
                    }
                },
            )
        else:
            self._logger.warning(
                "No guideline matches returned.",
                extra={"context": {"query": query_text}},
            )

        return [self._to_chunk(doc) for doc in top_results]

    def build_query_text(self, finding: Dict[str, object]) -> str:
        """Construct a natural-language retrieval query from finding attributes."""

        components: List[str] = []

        finding_type = finding.get("type") or finding.get("finding_type")
        if finding_type:
            components.append(str(finding_type))

        characteristics = finding.get("characteristics")
        if isinstance(characteristics, (list, tuple, set)):
            components.extend(str(item) for item in characteristics if item)
        elif characteristics:
            components.append(str(characteristics))

        size_mm = self._coerce_float(finding.get("size_mm"))
        if size_mm is not None:
            components.append(f"{size_mm:g}mm")

        location = finding.get("location") or finding.get("anatomical_location")
        if location:
            components.append(str(location))

        risk_level = self._normalize_risk(finding.get("risk_level"))
        if risk_level:
            components.append(f"{risk_level} risk patient")

        if not components:
            components.append("incidental imaging finding")

        components.append("follow-up recommendation")
        return " ".join(components)

    def rerank_results(
        self,
        results: Sequence[RetrievedDocument],
        finding: Dict[str, object],
    ) -> List[RetrievedDocument]:
        """Apply heuristic boosts to prioritize the best-aligned guideline chunks."""

        target_size = self._coerce_float(finding.get("size_mm"))
        risk_level = self._normalize_risk(finding.get("risk_level"))

        reranked: List[RetrievedDocument] = []
        for doc in results:
            score = doc.score
            metadata = doc.metadata

            size_min = self._coerce_float(metadata.get("size_min_mm"))
            size_max = self._coerce_float(metadata.get("size_max_mm"))

            if target_size is not None and size_min is not None and size_max is not None:
                if size_min <= target_size <= size_max:
                    score += 2.0
                else:
                    distance = min(abs(target_size - size_min), abs(target_size - size_max))
                    score -= min(distance / 10.0, 1.5)

            if risk_level:
                chunk_risk = metadata.get("risk_level")
                if chunk_risk and chunk_risk.lower() == risk_level:
                    score += 0.5

            reranked.append(
                RetrievedDocument(
                    id=doc.id,
                    text=doc.text,
                    score=score,
                    metadata=metadata,
                )
            )

        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_filters(self, finding: Dict[str, object]) -> Dict[str, object]:
        filters: Dict[str, object] = {}

        size_mm = self._coerce_float(finding.get("size_mm"))
        if size_mm is not None:
            filters["finding_size"] = size_mm

        risk_level = self._normalize_risk(finding.get("risk_level"))
        if risk_level:
            filters["patient_risk"] = risk_level

        sources = self._infer_sources(finding)
        if sources:
            filters["sources"] = sources

        return filters

    def _infer_sources(self, finding: Dict[str, object]) -> List[str]:
        text = " ".join(
            str(value).lower()
            for value in (
                finding.get("type"),
                finding.get("finding_type"),
                finding.get("organ"),
                finding.get("location"),
                finding.get("anatomical_location"),
            )
            if value
        )

        sources: List[str] = []
        if any(keyword in text for keyword in ("lung", "pulmon", "nodule")):
            sources.extend(
                [
                    "Fleischner Society Pulmonary Nodule Recommendations (2017)",
                    "ACR Lung-RADS® v2022 (Lung CT Screening Reporting & Data System)",
                ]
            )
        if any(keyword in text for keyword in ("liver", "hepatic")):
            sources.append(
                "ACR Incidental Findings Committee – Management of Incidental Liver Lesions on CT (2017)"
            )
        return sources

    def _to_chunk(self, document: RetrievedDocument) -> GuidelineChunk:
        metadata = document.metadata
        recommendation = metadata.get("recommendation") or self._extract_recommendation(document.text)
        citation = metadata.get("citation", "")

        return GuidelineChunk(
            chunk_id=document.id,
            text=document.text,
            source=str(metadata.get("source") or "Unknown source"),
            category=str(metadata.get("category") or "General"),
            size_min_mm=self._coerce_float(metadata.get("size_min_mm")),
            size_max_mm=self._coerce_float(metadata.get("size_max_mm")),
            risk_level=metadata.get("risk_level"),
            recommendation=recommendation,
            citation=citation,
            modality=metadata.get("modality"),
        )

    @staticmethod
    def _coerce_float(value: object) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_risk(value: object) -> Optional[str]:
        if not value:
            return None
        lowered = str(value).strip().lower()
        if "high" in lowered:
            return "high"
        if "intermediate" in lowered:
            return "intermediate"
        if "low" in lowered:
            return "low"
        return None

    @staticmethod
    def _extract_recommendation(text: str) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        if len(lines) <= 1:
            return text.strip()
        return "\n".join(lines[1:]).strip()

