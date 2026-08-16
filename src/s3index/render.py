"""Jinja2 environment setup and directory-index rendering."""

from pathlib import Path

from jinja2 import Environment, PackageLoader, Template, select_autoescape
from minio import Minio

from s3index.models import S3Object
from s3index.settings import Settings
from s3index.storage import upload_index, write_local_index


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
    client: Minio | None,
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> None:
    """Render an index for a directory, then write it.

    With `dry_run`, nothing is written. With `output_dir` set, the index
    is written to a local file instead of uploaded. Otherwise, it is
    uploaded to the bucket. A failed upload raises MinioException or
    HTTPError; the caller decides how to report it.
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
        return

    if output_dir is not None:
        write_local_index(output_dir, str(index_path), html)
        return

    assert client is not None, "a real S3 upload needs a Minio client"
    upload_index(client, settings.s3_bucket_name, str(index_path), html)
