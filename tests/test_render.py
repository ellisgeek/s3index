"""Tests for render_directory in render.py."""

import hashlib
from pathlib import PurePosixPath
from unittest.mock import MagicMock

import pytest

from s3index.models import S3Object
from s3index.render import build_environment, render_directory


@pytest.fixture
def template():
    return build_environment().get_template("default.html")


def make_dir(name: str = "dir", children: list | None = None) -> S3Object:
    dir_obj = S3Object(path=PurePosixPath(name), name=name, parent=PurePosixPath("."), is_dir=True)
    dir_obj.children = children or []
    return dir_obj


def test_render_directory_dry_run_writes_nothing(settings, template):
    client = MagicMock()

    render_directory(make_dir(), template, settings, client, dry_run=True)

    client.put_object.assert_not_called()


def test_render_directory_output_dir_writes_local_file(settings, template, tmp_path):
    client = MagicMock()

    render_directory(make_dir("mydir"), template, settings, client, output_dir=tmp_path)

    assert (tmp_path / "mydir" / "index.html").exists()
    client.put_object.assert_not_called()


def test_render_directory_uploads_by_default(settings, template):
    client = MagicMock()

    render_directory(make_dir(), template, settings, client)

    client.put_object.assert_called_once()


def test_render_directory_root_uses_bucket_index_name(settings, template, tmp_path):
    root = S3Object(path=PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
    client = MagicMock()

    render_directory(root, template, settings, client, output_dir=tmp_path)

    assert (tmp_path / "index.html").exists()


def test_render_directory_uploads_when_remote_etag_differs(settings, template):
    client = MagicMock()
    client.stat_object.return_value.etag = "not-a-real-hash"

    render_directory(make_dir(), template, settings, client)

    client.put_object.assert_called_once()


def test_render_directory_skips_upload_when_content_is_unchanged(settings, template):
    client = MagicMock()
    render_directory(make_dir(), template, settings, client)
    uploaded_html = client.put_object.call_args.args[2].getvalue().decode()
    matching_etag = hashlib.md5(uploaded_html.encode(), usedforsecurity=False).hexdigest()
    client.reset_mock()
    client.stat_object.return_value.etag = matching_etag

    render_directory(make_dir(), template, settings, client)

    client.put_object.assert_not_called()
    client.stat_object.assert_called_once()
