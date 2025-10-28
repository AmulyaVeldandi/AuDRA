"""Create demo follow-up orders and payloads for local development."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import typer

from src.parsers.fhir_parser import FHIRParser
from src.services.ehr_client import EHRClient
from src.tasks.fhir_builder import FHIRServiceRequestBuilder
from src.tasks.generator import TaskGenerator
from src.utils.logger import get_logger

app = typer.Typer(help="Seed mock EHR data and generated follow-up orders for demos.")

DEFAULT_REPORT_DIR = Path("data/sample_reports")
DEFAULT_OUTPUT = Path("data/seeded/service_requests.jsonl")

LOGGER = get_logger("scripts.seed_sample_data")


class SeedError(RuntimeError):
    """Raised when seeding fails."""


def _ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _iter_json_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.glob("*.json")):
        yield path


def _load_json(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - I/O guard
        raise SeedError(f"Failed to read sample file '{path}': {exc}") from exc


SAMPLE_RECIPES: Dict[str, Dict[str, Dict[str, object]]] = {
    "chest_ct_ggo_fhir": {
        "finding": {
            "type": "pulmonary_nodule",
            "size_mm": 12,
            "characteristics": ["ground-glass"],
            "location": "Right upper lobe",
            "risk_level": "low",
        },
        "recommendation": {
            "follow_up_type": "Low-dose CT chest",
            "timeframe_months": 6,
            "urgency": "routine",
            "reasoning": "Ground-glass opacity >=6 mm should be reassessed to confirm persistence.",
            "citation": "Fleischner Society 2017 - Subsolid nodules",
        },
    },
    "chest_ct_nodule_fhir": {
        "finding": {
            "type": "pulmonary_nodule",
            "size_mm": 8,
            "characteristics": ["solid"],
            "location": "Left lower lobe",
            "risk_level": "high",
        },
        "recommendation": {
            "follow_up_type": "CT chest with contrast",
            "timeframe_months": 3,
            "urgency": "urgent",
            "reasoning": "Solid pulmonary nodule 8 mm with high-risk features merits short interval imaging.",
            "citation": "Fleischner Society 2017 - Solid nodules",
        },
    },
    "liver_mri_lesion_fhir": {
        "finding": {
            "type": "hepatic_lesion",
            "size_mm": 15,
            "characteristics": ["hypervascular"],
            "location": "Hepatic segment VIII",
            "risk_level": "intermediate",
        },
        "recommendation": {
            "follow_up_type": "MRI liver with hepatobiliary contrast",
            "timeframe_months": 6,
            "urgency": "routine",
            "reasoning": "Hypervascular 1.5 cm lesion warrants interval MRI per ACR incidental liver lesion guidance.",
            "citation": "ACR Incidental Liver Lesions 2017",
        },
    },
}


def _resolve_recipe(stem: str) -> Optional[Dict[str, Dict[str, object]]]:
    return SAMPLE_RECIPES.get(stem)


def _derive_patient_id(reference: Optional[str], fallback: str = "patient-demo") -> str:
    if not reference:
        return fallback
    return reference.split("/")[-1] or fallback


@app.command("run")
def run(
    reports_dir: Path = typer.Option(
        DEFAULT_REPORT_DIR,
        "--reports-dir",
        "-r",
        help="Directory containing sample DiagnosticReport JSON files.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="Path to write generated ServiceRequest records (JSON Lines).",
    ),
    base_url: str = typer.Option(
        "http://mock-ehr.local",
        "--ehr-base-url",
        help="Base URL for remote EHR integration (ignored when --mock is used).",
    ),
    mock: bool = typer.Option(
        True,
        "--mock/--remote",
        help="Use the built-in mock EHR (default) or call a real FHIR endpoint.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Do not persist anything; print the payloads that would be stored.",
    ),
) -> None:
    """
    Generate example follow-up ServiceRequests for the bundled sample reports.
    """

    reports_dir = reports_dir.resolve()
    if not reports_dir.exists():
        typer.secho(f"Sample report directory not found: {reports_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    parser = FHIRParser()
    generator = TaskGenerator()
    builder = FHIRServiceRequestBuilder()
    ehr_client = EHRClient(base_url=base_url, use_mock=mock)

    created_records: List[Dict[str, object]] = []

    for file_path in _iter_json_files(reports_dir):
        stem = file_path.stem
        recipe = _resolve_recipe(stem)
        if recipe is None:
            LOGGER.warning(
                "Skipping sample without recipe.",
                extra={"context": {"file": str(file_path)}},
            )
            continue

        payload = _load_json(file_path)
        report_id = payload.get("id") or stem
        patient_ref = payload.get("subject", {}).get("reference")
        patient_id = _derive_patient_id(patient_ref)

        try:
            report_text, patient_meta = parser.parse_diagnostic_report(payload)
        except ValueError as exc:
            LOGGER.error(
                "Failed to parse DiagnosticReport.",
                extra={"context": {"file": str(file_path), "error": str(exc)}},
            )
            continue

        if patient_meta.get("patient_id"):
            patient_id = patient_meta["patient_id"] or patient_id

        try:
            task = generator.generate_task(
                recipe["recommendation"],
                recipe["finding"],
                patient_id=patient_id,
            )
        except ValueError as exc:
            LOGGER.error(
                "Could not generate follow-up task.",
                extra={"context": {"file": str(file_path), "error": str(exc)}},
            )
            continue

        service_request = builder.build_service_request(
            task,
            diagnostic_report_id=report_id,
        )

        order_id: str
        if dry_run:
            order_id = task.task_id
        else:
            order_id = ehr_client.create_service_request(service_request)
            service_request["id"] = order_id

        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {
            "created_at": created_at,
            "report_file": str(file_path),
            "report_id": report_id,
            "order_id": order_id,
            "patient_id": patient_id,
            "task": task.to_dict(),
            "service_request": service_request,
            "report_excerpt": report_text[:280],
            "patient_metadata": patient_meta,
            "mode": "mock" if mock else "remote",
        }
        created_records.append(record)

        typer.secho(
            f"Generated follow-up order {order_id} for report {report_id} ({stem}).",
            fg=typer.colors.GREEN,
        )

    if not created_records:
        typer.echo("No sample records were generated.")
        return

    if dry_run:
        typer.echo("Dry run complete; nothing persisted.")
        return

    _ensure_directory(output_path)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in created_records:
            handle.write(json.dumps(record, default=str))
            handle.write("\n")

    typer.echo(f"Wrote {len(created_records)} records to {output_path}.")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    app()
