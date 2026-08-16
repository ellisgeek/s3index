"""Jinja2 environment setup and directory-index rendering."""

from jinja2 import Environment, PackageLoader, Template, select_autoescape
from minio import Minio

from s3index.models import S3Object
from s3index.settings import Settings
from s3index.storage import upload_index


def build_environment() -> Environment:
    """Build the Jinja2 environment that loads templates from the package.

    `package_path` points at the repo-root `templates/` directory, since
    that directory does not live under `src/s3index/` yet.
    """
    return Environment(
        loader=PackageLoader("s3index", package_path="../../templates"),
        autoescape=select_autoescape(),
    )


def render_directory(dir_obj: S3Object, template: Template, settings: Settings, client: Minio) -> None:
    """Render an index for a directory and upload it."""
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

    print(f"Uploading index for {dir_obj.path or '/'} -> {index_path}")
    upload_index(client, settings.s3_bucket_name, str(index_path), html)
