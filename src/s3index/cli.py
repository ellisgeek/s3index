"""Orchestrates listing S3 objects and generating directory-index pages."""

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional

import typer
from jinja2 import Template
from minio import Minio
from minio.error import MinioException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from s3index.models import S3Object, build_tree, resolve_content_types
from s3index.render import EXIT_S3_ERROR, build_environment, render_directory
from s3index.settings import Settings
from s3index.storage import list_all_objects

EXIT_CONFIG_ERROR = 1

app = typer.Typer()


def render_all(
    dir_objs: Iterable[S3Object],
    template: Template,
    settings: Settings,
    client: Minio,
    dry_run: bool,
    output_dir: Optional[Path],
) -> None:
    """Render each directory index concurrently.

    Stops scheduling new uploads as soon as one fails, and re-raises that
    failure's error from the main thread.
    """
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(render_directory, obj, template, settings, client, dry_run, output_dir): obj
            for obj in dir_objs
        }
        for future in as_completed(futures):
            try:
                future.result()
            except typer.Exit:
                for f in futures:
                    f.cancel()
                raise


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
) -> None:
    """Generate static HTML directory-index pages for an S3-compatible bucket."""
    if dry_run and output_dir is not None:
        typer.echo("Error: --dry-run and --output-dir cannot be used together.", err=True)
        raise typer.Exit(code=EXIT_CONFIG_ERROR)

    try:
        settings = Settings(_env_file=env_file) if env_file else Settings()  # type: ignore
    except ValidationError as e:
        missing = [str(err["loc"][0]).upper() for err in e.errors() if err["type"] == "missing"]
        if missing:
            typer.echo(f"Error: missing config: {', '.join(missing)}", err=True)
        else:
            typer.echo(f"Error: invalid config: {e}", err=True)
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

    env = build_environment()
    tmpl = env.get_template(settings.template or "default.html")

    print("Listing S3 objects...")
    try:
        all_objects = list_all_objects(client, settings.s3_bucket_name, settings.s3_bucket_prefix)
    except (MinioException, HTTPError) as e:
        typer.echo(f"Error: could not list objects in bucket '{settings.s3_bucket_name}': {e}", err=True)
        raise typer.Exit(code=EXIT_S3_ERROR) from e

    dirs, all_entries = build_tree(all_objects, settings, client)

    print("Resolving content types...")
    resolve_content_types(all_entries.values())

    print("Computing directory sizes...")
    for dir_obj in dirs.values():
        dir_obj.compute_totals()

    render_all(dirs.values(), tmpl, settings, client, dry_run, output_dir)

    if settings.s3_bucket_prefix:
        try:
            root_dir = dirs[PurePosixPath(settings.s3_bucket_prefix)]
        except KeyError as e:
            typer.echo(
                f"Error: configured S3_BUCKET_PREFIX {settings.s3_bucket_prefix!r} "
                "not found among listed objects.",
                err=True,
            )
            raise typer.Exit(code=EXIT_S3_ERROR) from e
    else:
        root_dir = S3Object(PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
        root_dir.children = [x for x in all_entries.values() if x.parent == PurePosixPath(".")]
        _ = root_dir.compute_totals()

    render_directory(root_dir, tmpl, settings, client, dry_run, output_dir)

    print("All directory indexes generated successfully.")


if __name__ == "__main__":
    app()
