"""Tests for the Minio wrapper functions in storage.py, against a mocked client."""

from unittest.mock import MagicMock

from conftest import make_object
from minio.error import S3Error

from s3index.storage import (
    fetch_prefix_bytes,
    get_remote_etag,
    list_all_objects,
    list_buckets,
    list_top_level_prefixes,
    upload_index,
    write_local_index,
)


def test_list_all_objects_passes_through_recursive_listing():
    client = MagicMock()
    client.list_objects.return_value = [make_object("a.txt"), make_object("b.txt")]

    result = list_all_objects(client, "bucket", "prefix/")

    client.list_objects.assert_called_once_with("bucket", "prefix/", recursive=True)
    assert [o.object_name for o in result] == ["a.txt", "b.txt"]


def test_fetch_prefix_bytes_reads_and_releases_the_response():
    response = MagicMock()
    response.read.return_value = b"hello"
    client = MagicMock()
    client.get_object.return_value = response

    data = fetch_prefix_bytes(client, "bucket", "a.txt", length=5)

    assert data == b"hello"
    client.get_object.assert_called_once_with("bucket", "a.txt", offset=0, length=5)
    response.close.assert_called_once()
    response.release_conn.assert_called_once()


def test_upload_index_puts_html_with_correct_content_type():
    client = MagicMock()

    upload_index(client, "bucket", "index.html", "<html></html>")

    args, kwargs = client.put_object.call_args
    assert args[0] == "bucket"
    assert args[1] == "index.html"
    assert kwargs["content_type"] == "text/html"


def test_write_local_index_creates_parent_dirs_and_writes_file(tmp_path):
    write_local_index(tmp_path, "a/b/index.html", "<html>hi</html>")

    written = tmp_path / "a" / "b" / "index.html"
    assert written.read_text(encoding="utf-8") == "<html>hi</html>"


def test_list_buckets_passes_through():
    client = MagicMock()
    client.list_buckets.return_value = ["bucket-a", "bucket-b"]

    assert list_buckets(client) == ["bucket-a", "bucket-b"]


def test_list_top_level_prefixes_returns_only_directory_entries():
    client = MagicMock()
    client.list_objects.return_value = [make_object("dir/"), make_object("file.txt")]

    result = list_top_level_prefixes(client, "bucket", "")

    assert result == ["dir/"]


def test_get_remote_etag_returns_the_etag():
    client = MagicMock()
    client.stat_object.return_value.etag = "abc123"

    assert get_remote_etag(client, "bucket", "index.html") == "abc123"


def test_get_remote_etag_returns_none_when_object_is_missing():
    client = MagicMock()
    client.stat_object.side_effect = S3Error("NoSuchKey", "not found", None, None, None, MagicMock())

    assert get_remote_etag(client, "bucket", "index.html") is None
