"""Blocks every Minio write call, for safe manual testing against a real endpoint.

Call `install()` before exercising s3index against a real S3 endpoint. Any
write attempt then raises `BlockedWriteError` instead of running for real.
Read-only calls (list_objects, get_object, stat_object, list_buckets, ...)
are left untouched.
"""

from unittest.mock import patch

from minio import Minio

WRITE_METHODS = [
    "copy_object",
    "delete_bucket_encryption",
    "delete_bucket_lifecycle",
    "delete_bucket_notification",
    "delete_bucket_policy",
    "delete_bucket_replication",
    "delete_bucket_tags",
    "delete_object_lock_config",
    "delete_object_tags",
    "fput_object",
    "make_bucket",
    "put_object",
    "remove_bucket",
    "remove_object",
    "remove_objects",
    "set_bucket_encryption",
    "set_bucket_lifecycle",
    "set_bucket_notification",
    "set_bucket_policy",
    "set_bucket_replication",
    "set_bucket_tags",
    "set_bucket_versioning",
    "set_object_lock_config",
    "set_object_retention",
    "set_object_tags",
    "upload_snowball_objects",
]


class BlockedWriteError(RuntimeError):
    """Raised when code calls a real S3 write while the dev guard is active."""


def _make_blocked(name: str):
    def _raise(self, *args, **kwargs):
        raise BlockedWriteError(
            f"Blocked a real S3 write: Minio.{name}(). Use --output-dir or --dry-run instead."
        )

    return _raise


def install() -> list:
    """Patch every Minio write method to raise instead of running for real.

    Returns the list of active patchers. Call `.stop()` on each only for a
    deliberate, explicitly approved real run.
    """
    patchers = [patch.object(Minio, name, new=_make_blocked(name)) for name in WRITE_METHODS]
    for patcher in patchers:
        patcher.start()
    return patchers
