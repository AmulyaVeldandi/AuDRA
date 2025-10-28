"""CLI utility for populating the guideline vector index."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer

from src.guidelines.indexer import GuidelineIndexer
from src.services.nim_embeddings import EmbeddingClient, NIMServiceError
from src.services.vector_store import VectorStore, VectorStoreError
from src.utils.config import get_settings
from src.utils.logger import get_logger

app = typer.Typer(help="Index medical guideline markdown files into the vector store.")

DEFAULT_GUIDELINE_DIR = Path("data/guidelines")


def _refresh_settings() -> None:
    """Reload cached settings so newly-set env vars are respected."""

    # get_settings is lru-cached; clear so changes take effect for scripts.
    get_settings.cache_clear()  # type: ignore[attr-defined]
    get_settings()


def _normalise_dir(value: Optional[Path]) -> Path:
    if value is None:
        return DEFAULT_GUIDELINE_DIR
    return value.resolve()


@app.command("run")
def run(
    guidelines_dir: Optional[Path] = typer.Option(
        None,
        "--guidelines-dir",
        "-g",
        help="Directory containing guideline markdown files.",
    ),
    index_name: str = typer.Option(
        "medical_guidelines",
        "--index-name",
        help="Target vector store index name.",
    ),
    batch_size: int = typer.Option(
        50,
        "--batch-size",
        min=1,
        max=500,
        help="Number of chunks to upsert per bulk request.",
    ),
    drop_existing: bool = typer.Option(
        False,
        "--drop-existing",
        help="Delete and recreate the target index before ingesting content.",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Force local OpenSearch endpoint (http://localhost:9200).",
    ),
) -> None:
    """
    Load markdown guidelines, create embeddings with the NV-Embed NIM, and push
    the documents into the configured OpenSearch index.
    """

    guideline_path = _normalise_dir(guidelines_dir)
    if not guideline_path.exists():
        typer.secho(f"Guideline directory not found: {guideline_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if local:
        os.environ.setdefault("OPENSEARCH_ENDPOINT", "http://localhost:9200")

    _refresh_settings()
    logger = get_logger("scripts.index_guidelines")

    try:
        embedding_client = EmbeddingClient()
    except NIMServiceError as exc:
        typer.secho(f"Embedding client initialisation failed: {exc}", fg=typer.colors.RED, err=True)
        typer.echo(
            "Verify NIM_EMBEDDING_ENDPOINT and NIM_EMBEDDING_API_KEY are set in your environment or .env file."
        )
        raise typer.Exit(code=2) from exc

    try:
        vector_store = VectorStore(index_name=index_name)
    except VectorStoreError as exc:
        typer.secho(f"Vector store initialisation failed: {exc}", fg=typer.colors.RED, err=True)
        typer.echo("Check OPENSEARCH_ENDPOINT, AWS_REGION, and credentials.")
        raise typer.Exit(code=3) from exc

    if drop_existing:
        typer.echo(f"Dropping existing index '{index_name}'...")
        try:
            vector_store.delete_index()
        except VectorStoreError as exc:
            typer.secho(f"Failed to delete index '{index_name}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=4) from exc
        # Recreate the index by instantiating a fresh client.
        vector_store = VectorStore(index_name=index_name)

    indexer = GuidelineIndexer()
    typer.echo(
        f"Indexing guidelines from {guideline_path} into '{index_name}' "
        f"(batch_size={batch_size})..."
    )

    try:
        indexer.index_all_guidelines(
            str(guideline_path),
            embedding_client=embedding_client,
            vector_store=vector_store,
            batch_size=batch_size,
        )
    except (NIMServiceError, VectorStoreError, FileNotFoundError, ValueError) as exc:
        logger.error(
            "Guideline indexing failed.",
            extra={"context": {"error": str(exc)}},
        )
        typer.secho(f"Indexing failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=5) from exc

    typer.secho("Guideline indexing complete.", fg=typer.colors.GREEN)


def main(argv: Optional[list[str]] = None) -> None:
    """Entrypoint compatible with python -m execution."""

    app(standalone_mode=True, prog_name="index-guidelines", args=argv or sys.argv[1:])


if __name__ == "__main__":
    main()
