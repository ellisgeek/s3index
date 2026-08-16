"""Shared pytest fixtures for the s3index test suite."""

from datetime import datetime, timezone

import pytest
from minio.datatypes import Object

from s3index.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        s3_endpoint="s3.example.com",
        s3_bucket_name="test-bucket",
        s3_bucket_prefix="",
        s3_access_key="key",
        s3_secret_key="secret",
    )


def make_object(name: str, size: int = 100, last_modified: datetime | None = None) -> Object:
    """Build a fake minio listing entry, as returned by `client.list_objects()`."""
    return Object(
        bucket_name="test-bucket",
        object_name=name,
        size=size,
        last_modified=last_modified or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
