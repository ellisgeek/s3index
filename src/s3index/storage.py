"""Minio wrapper: listing, uploads, content-sniffing, and bucket/prefix browsing."""

from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.datatypes import Bucket, Object
from minio.error import MinioException
from urllib3.exceptions import HTTPError


def list_all_objects(client: Minio, bucket_name: str, prefix: str) -> list[Object]:
    """List every object under a prefix, recursively."""
    return list(client.list_objects(bucket_name, prefix, recursive=True))


def fetch_prefix_bytes(client: Minio, bucket_name: str, object_name: str, length: int = 2048) -> bytes:
    """Fetch the first `length` bytes of an object, for content-type sniffing."""
    response = client.get_object(bucket_name, object_name, offset=0, length=length)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def get_remote_etag(client: Minio, bucket_name: str, object_name: str) -> str | None:
    """Get an existing object's ETag, or None if it cannot be determined.

    A missing object, a permissions error, or a connection failure all
    return None here, so the caller falls back to uploading.
    """
    try:
        return client.stat_object(bucket_name, object_name).etag
    except (MinioException, HTTPError):
        return None


def upload_index(client: Minio, bucket_name: str, object_name: str, html: str) -> None:
    """Upload rendered directory-index HTML as an object."""
    raw = BytesIO(html.encode())
    client.put_object(
        bucket_name,
        object_name,
        raw,
        length=len(raw.getvalue()),
        content_type="text/html",
    )


def write_local_index(output_dir: Path, object_name: str, html: str) -> None:
    """Write rendered directory-index HTML to a local file, mirroring the object path."""
    path = output_dir / object_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def list_buckets(client: Minio) -> list[Bucket]:
    """List all buckets visible to the configured credentials."""
    return client.list_buckets()


def list_top_level_prefixes(client: Minio, bucket_name: str, prefix: str = "") -> list[str]:
    """List the immediate subdirectory prefixes under `prefix` in a bucket."""
    return [
        obj.object_name
        for obj in client.list_objects(bucket_name, prefix=prefix, recursive=False)
        if obj.object_name and obj.is_dir
    ]
