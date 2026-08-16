"""Minio wrapper: listing, uploads, content-sniffing, and bucket/prefix browsing."""

from io import BytesIO

from minio import Minio
from minio.datatypes import Bucket, Object


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


def list_buckets(client: Minio) -> list[Bucket]:
    """List all buckets visible to the configured credentials."""
    return client.list_buckets()


def list_top_level_prefixes(client: Minio, bucket_name: str, prefix: str = "") -> list[str]:
    """List the immediate subdirectory prefixes under `prefix` in a bucket."""
    return [
        obj.object_name
        for obj in client.list_objects(bucket_name, prefix=prefix, delimiter="/")
        if obj.object_name and obj.is_dir
    ]
