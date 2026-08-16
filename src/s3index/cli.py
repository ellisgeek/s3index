"""Orchestrates listing S3 objects and generating directory-index pages."""

import sys
from collections import Counter
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import questionary
import typer
from jinja2 import Template
from minio import Minio
from minio.error import MinioException
from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from urllib3.exceptions import HTTPError

from s3index.models import S3Object, build_tree, resolve_content_types
from s3index.render import RenderResult, build_environment, render_directory
from s3index.settings import Settings
from s3index.storage import list_all_objects, list_buckets, list_top_level_prefixes

EXIT_CONFIG_ERROR = 1
EXIT_S3_ERROR = 2
USE_CURRENT_LEVEL = "(use this level)"

app = typer.Typer(pretty_exceptions_enable=False)
console = Console()
error_console = Console(stderr=True)


def _progress() -> Progress:
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def render_all(
    dir_objs: Collection[S3Object],
    template: Template,
    settings: Settings,
    client: Optional[Minio],
    dry_run: bool,
    output_dir: Optional[Path],
) -> list[RenderResult]:
    """Render each directory index concurrently, with a progress bar.

    Stops scheduling new uploads as soon as one fails, reports it, and
    exits. Returns what happened to each index.
    """
    results: list[RenderResult] = []
    with ThreadPoolExecutor() as executor, _progress() as progress:
        task = progress.add_task("Rendering indexes...", total=len(dir_objs))
        futures = {
            executor.submit(render_directory, obj, template, settings, client, dry_run, output_dir): obj
            for obj in dir_objs
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except (MinioException, HTTPError) as e:
                dir_obj = futures[future]
                for f in futures:
                    f.cancel()
                progress.stop()
                error_console.print(f"[red]Error:[/red] failed to upload index for {dir_obj.path or '/'}: {e}")
                raise typer.Exit(code=EXIT_S3_ERROR) from e
            progress.advance(task)
    return results


def summarize_results(results: list[RenderResult]) -> str:
    """Describe what happened across a batch of render results, as one line."""
    counts = Counter(results)
    if counts[RenderResult.DRY_RUN]:
        return f"Would write {counts[RenderResult.DRY_RUN]} indexes."
    if counts[RenderResult.WRITTEN]:
        return f"Wrote {counts[RenderResult.WRITTEN]} indexes."
    return f"Uploaded {counts[RenderResult.UPLOADED]} indexes, skipped {counts[RenderResult.SKIPPED]} unchanged."


def _pick_bucket(client: Minio) -> str:
    """Prompt for a bucket name via an arrow-key menu."""
    try:
        buckets = list_buckets(client)
    except (MinioException, HTTPError) as e:
        error_console.print(f"[red]Error:[/red] could not list buckets: {e}")
        raise typer.Exit(code=EXIT_S3_ERROR) from e

    choice = questionary.select("Select a bucket:", choices=[b.name for b in buckets]).ask()
    if choice is None:
        error_console.print("[red]Error:[/red] no bucket selected.")
        raise typer.Exit(code=EXIT_CONFIG_ERROR)
    return choice


def _pick_prefix(client: Minio, bucket_name: str) -> str:
    """Prompt for a starting prefix, browsing one subfolder level at a time."""
    prefix = ""
    while True:
        try:
            subdirs = list_top_level_prefixes(client, bucket_name, prefix)
        except (MinioException, HTTPError) as e:
            error_console.print(f"[red]Error:[/red] could not list '{prefix or '/'}': {e}")
            raise typer.Exit(code=EXIT_S3_ERROR) from e

        if not subdirs:
            return prefix

        choice = questionary.select(
            f"Browse into a subfolder of '{prefix or '/'}':",
            choices=[USE_CURRENT_LEVEL, *subdirs],
        ).ask()
        if choice is None:
            error_console.print("[red]Error:[/red] no prefix selected.")
            raise typer.Exit(code=EXIT_CONFIG_ERROR)
        if choice == USE_CURRENT_LEVEL:
            return prefix
        prefix = choice


@app.command()
def main(
    s3_endpoint: Annotated[Optional[str], typer.Option(help="S3 endpoint hostname.")] = None,
    s3_bucket_name: Annotated[Optional[str], typer.Option(help="Bucket to index.")] = None,
    s3_bucket_prefix: Annotated[Optional[str], typer.Option(help="Prefix within the bucket to index.")] = None,
    s3_scheme: Annotated[Optional[str], typer.Option(help="URL scheme for object links.")] = None,
    template: Annotated[Optional[str], typer.Option(help="Template file name.")] = None,
    index_name: Annotated[Optional[str], typer.Option(help="File name for generated index pages.")] = None,
    env_file: Annotated[Optional[Path], typer.Option(help="Path to a .env file to load config from.")] = None,
    dry_run: Annotated[bool, typer.Option(help="Build and render indexes without writing them anywhere.")] = False,
    output_dir: Annotated[
        Optional[Path], typer.Option(help="Write index files to this local directory instead of uploading them.")
    ] = None,
    interactive: Annotated[
        Optional[bool],
        typer.Option(
            "--interactive/--no-interactive",
            help="Prompt for a bucket/prefix when unset. Defaults to on in a terminal if no bucket is configured.",
        ),
    ] = None,
) -> None:
    """Generate static HTML directory-index pages for an S3-compatible bucket."""
    if dry_run and output_dir is not None:
        error_console.print("[red]Error:[/red] --dry-run and --output-dir cannot be used together.")
        raise typer.Exit(code=EXIT_CONFIG_ERROR)

    try:
        settings = Settings(_env_file=env_file) if env_file else Settings()
    except ValidationError as e:
        missing = [str(err["loc"][0]).upper() for err in e.errors() if err["type"] == "missing"]
        if missing:
            error_console.print(f"[red]Error:[/red] missing config: {', '.join(missing)}")
        else:
            error_console.print(f"[red]Error:[/red] invalid config: {e}")
        raise typer.Exit(code=EXIT_CONFIG_ERROR) from e

    overrides = {
        "s3_endpoint": s3_endpoint,
        "s3_bucket_name": s3_bucket_name,
        "s3_bucket_prefix": s3_bucket_prefix,
        "s3_scheme": s3_scheme,
        "template": template,
        "index_name": index_name,
    }
    for field_name, value in overrides.items():
        if value is not None:
            setattr(settings, field_name, value)

    client = Minio(
        str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    should_prompt = interactive if interactive is not None else (not settings.s3_bucket_name and sys.stdout.isatty())
    if should_prompt:
        if not settings.s3_bucket_name:
            settings.s3_bucket_name = _pick_bucket(client)
        if not settings.s3_bucket_prefix:
            settings.s3_bucket_prefix = _pick_prefix(client, settings.s3_bucket_name)

    if not settings.s3_bucket_name:
        error_console.print("[red]Error:[/red] missing config: S3_BUCKET_NAME")
        raise typer.Exit(code=EXIT_CONFIG_ERROR)

    env = build_environment()
    tmpl = env.get_template(settings.template or "default.html")

    console.print("Listing S3 objects...")
    try:
        all_objects = list_all_objects(client, settings.s3_bucket_name, settings.s3_bucket_prefix)
    except (MinioException, HTTPError) as e:
        error_console.print(f"[red]Error:[/red] could not list objects in bucket '{settings.s3_bucket_name}': {e}")
        raise typer.Exit(code=EXIT_S3_ERROR) from e

    dirs, all_entries = build_tree(all_objects, settings, client)
    file_count = sum(1 for obj in all_entries.values() if not obj.is_dir)

    with _progress() as progress:
        task = progress.add_task("Resolving content types...", total=file_count)
        resolve_content_types(all_entries.values(), on_progress=lambda: progress.advance(task))

    console.print("Computing directory sizes...")
    for dir_obj in dirs.values():
        dir_obj.compute_totals()

    if settings.s3_bucket_prefix:
        if PurePosixPath(settings.s3_bucket_prefix) not in dirs:
            error_console.print(
                f"[red]Error:[/red] configured S3_BUCKET_PREFIX {settings.s3_bucket_prefix!r} "
                "not found among listed objects."
            )
            raise typer.Exit(code=EXIT_S3_ERROR)
        render_targets = list(dirs.values())
    else:
        root_dir = S3Object(PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
        root_dir.children = [x for x in all_entries.values() if x.parent == PurePosixPath(".")]
        _ = root_dir.compute_totals()
        render_targets = [*dirs.values(), root_dir]

    results = render_all(render_targets, tmpl, settings, client, dry_run, output_dir)

    console.print(summarize_results(results))


if __name__ == "__main__":
    app()
