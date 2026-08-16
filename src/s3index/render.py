"""Jinja2 environment setup and directory-index rendering."""

from pathlib import Path

import typer
from jinja2 import Environment, PackageLoader, Template, select_autoescape
from minio import Minio
from minio.error import MinioException
from urllib3.exceptions import HTTPError

from s3index.models import S3Object
from s3index.settings import Settings
from s3index.storage import upload_index, write_local_index

EXIT_S3_ERROR = 2


def build_environment() -> Environment:
    """Build the Jinja2 environment that loads templates from the package.

    `package_path` points at the repo-root `templates/` directory, since
    that directory does not live under `src/s3index/` yet.
    """
    return Environment(
        loader=PackageLoader("s3index", package_path="../../templates"),
        autoescape=select_autoescape(),
    )


def render_directory(
    dir_obj: S3Object,
    template: Template,
    settings: Settings,
    client: Minio,
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> None:
    """Render an index for a directory, then write it.

    With `dry_run`, nothing is written. With `output_dir` set, the index
    is written to a local file instead of uploaded. Otherwise, it is
    uploaded to the bucket.
    """
    objects = sorted(dir_obj.children, key=lambda x: (not x.is_dir, x.name.lower()))

    is_root = (
        str(dir_obj.path).rstrip("/") == str(settings.s3_bucket_prefix).rstrip("/") or str(dir_obj.path) == "."
    )
    parent_link = None if is_root else "../index.html"

    html = template.render(
        objects=objects,
        current_dir=dir_obj.path if not is_root else "/",
        parent_link=parent_link,
        bucket_name=settings.s3_bucket_name,
        endpoint=settings.s3_endpoint,
        bucket_prefix=settings.s3_bucket_prefix,
        total_bytes=dir_obj.total_bytes,
        total_size=dir_obj.total_size,
    )

    index_path = f"{dir_obj.path}/{settings.index_name}" if not is_root else settings.index_name

    if dry_run:
        print(f"Would write index for {dir_obj.path or '/'} -> {index_path}")
        return

    if output_dir is not None:
        print(f"Writing index for {dir_obj.path or '/'} -> {output_dir / index_path}")
        write_local_index(output_dir, str(index_path), html)
        return

    print(f"Uploading index for {dir_obj.path or '/'} -> {index_path}")
    try:
        upload_index(client, settings.s3_bucket_name, str(index_path), html)
    except (MinioException, HTTPError) as e:
        typer.echo(f"Error: failed to upload index for {dir_obj.path or '/'}: {e}", err=True)
        raise typer.Exit(code=EXIT_S3_ERROR) from e
