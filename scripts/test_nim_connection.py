"""Validate connectivity to NVIDIA NIM endpoints used by AuDRA-Rad."""

from __future__ import annotations

import sys
import time
from typing import Optional

import typer

from src.utils.config import get_settings
from src.utils.logger import get_logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from src.services.nim_embeddings import EmbeddingClient  # noqa: F401
    from src.services.nim_llm import NemotronClient  # noqa: F401

app = typer.Typer(help="Smoke-test Nemotron (LLM) and NV-Embed connectivity.")


def _refresh_settings() -> None:
    get_settings.cache_clear()  # type: ignore[attr-defined]
    get_settings()


@app.command("run")
def run(
    sample_text: str = typer.Option(
        "Connectivity check for AuDRA-Rad.",
        "--text",
        "-t",
        help="Sample text to embed and summarise.",
    ),
    include_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Skip Nemotron validation if not available.",
    ),
    include_embeddings: bool = typer.Option(
        True,
        "--embeddings/--no-embeddings",
        help="Skip NV-Embed validation if not available.",
    ),
) -> None:
    """
    Perform lightweight requests against the configured NIM services and
    report latency and key metadata.
    """

    logger = get_logger("scripts.test_nim_connection")
    _refresh_settings()

    if not include_embeddings and not include_llm:
        typer.secho("Nothing to test. Enable at least one NIM check.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    if include_embeddings:
        from src.services.nim_embeddings import EmbeddingClient, NIMServiceError as EmbeddingError  # noqa: WPS433

        try:
            embed_client = EmbeddingClient()
        except EmbeddingError as exc:
            typer.secho(f"Embedding client initialisation failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc

        typer.echo("Testing NV-Embed endpoint...")
        start = time.perf_counter()
        try:
            vector = embed_client.embed_text(sample_text)
        except EmbeddingError as exc:
            logger.error(
                "Embedding request failed.",
                extra={"context": {"error": str(exc)}},
            )
            typer.secho(f"Embedding request failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=3) from exc
        latency_ms = (time.perf_counter() - start) * 1000.0
        preview = ", ".join(f"{value:.4f}" for value in vector[:5])
        typer.secho(
            f"NV-Embed OK ({latency_ms:.1f} ms, dim={len(vector)}). Sample: [{preview}]",
            fg=typer.colors.GREEN,
        )

    if include_llm:
        from src.services.nim_llm import NemotronClient, NIMServiceError as LLMError  # noqa: WPS433

        try:
            llm_client = NemotronClient()
        except LLMError as exc:
            typer.secho(f"Nemotron client initialisation failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=4) from exc

        prompt = (
            "Respond with a one-sentence acknowledgement that includes the phrase 'NIM connection confirmed'."
        )
        typer.echo("Testing Nemotron endpoint...")
        start = time.perf_counter()
        try:
            response = llm_client.generate(prompt, temperature=0.0, max_tokens=40)
        except LLMError as exc:
            logger.error(
                "Nemotron request failed.",
                extra={"context": {"error": str(exc)}},
            )
            typer.secho(f"Nemotron request failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=5) from exc

        latency_ms = (time.perf_counter() - start) * 1000.0
        typer.secho(
            f"Nemotron OK ({latency_ms:.1f} ms): {response.strip()}",
            fg=typer.colors.GREEN,
        )

    typer.secho("NIM connectivity checks complete.", fg=typer.colors.GREEN)


def main(argv: Optional[list[str]] = None) -> None:
    app(standalone_mode=True, prog_name="test-nim-connection", args=argv or sys.argv[1:])


if __name__ == "__main__":
    main()
