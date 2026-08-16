"""Tests for S3Object and tree-building in models.py."""

from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

from conftest import make_object
from minio.error import S3Error

from s3index.models import S3Object, _sniff_content_type, build_tree, resolve_content_types


def test_from_minio_sets_path_name_and_parent(settings):
    obj = S3Object.from_minio(make_object("a/b/c.txt"), settings, client=None)

    assert obj.path == PurePosixPath("a/b/c.txt")
    assert obj.name == "c.txt"
    assert obj.parent == PurePosixPath("a/b")
    assert not obj.is_dir


def test_from_minio_builds_s3url(settings):
    obj = S3Object.from_minio(make_object("a.txt"), settings, client=None)

    assert str(obj.s3url) == "https://s3.example.com/test-bucket/a.txt"


def test_link_appends_index_html_for_directories():
    file_obj = S3Object(path=PurePosixPath("a.txt"), name="a.txt", parent=PurePosixPath("."))
    dir_obj = S3Object(path=PurePosixPath("dir"), name="dir", parent=PurePosixPath("."), is_dir=True)

    assert file_obj.link == "a.txt"
    assert dir_obj.link == "dir/index.html"


def test_relpath_strips_configured_prefix():
    obj = S3Object(
        path=PurePosixPath("root/a.txt"),
        name="a.txt",
        parent=PurePosixPath("root"),
        _bucket_prefix="root",
    )

    assert obj.relpath == PurePosixPath("a.txt")


def test_compute_totals_sums_children_recursively():
    leaf1 = S3Object(path=PurePosixPath("d/a.txt"), name="a.txt", parent=PurePosixPath("d"), bytes=10)
    leaf2 = S3Object(path=PurePosixPath("d/b.txt"), name="b.txt", parent=PurePosixPath("d"), bytes=20)
    inner = S3Object(path=PurePosixPath("d/sub"), name="sub", parent=PurePosixPath("d"), is_dir=True)
    leaf3 = S3Object(path=PurePosixPath("d/sub/c.txt"), name="c.txt", parent=PurePosixPath("d/sub"), bytes=5)
    inner.children = [leaf3]
    root = S3Object(path=PurePosixPath("d"), name="d", parent=PurePosixPath("."), is_dir=True)
    root.children = [leaf1, leaf2, inner]

    total = root.compute_totals()

    assert total == 35
    assert root.total_bytes == 35
    assert inner.total_bytes == 5


def test_build_tree_creates_virtual_directories(settings):
    objects = [make_object("a/b/c.txt"), make_object("a/d.txt")]

    dirs, all_entries = build_tree(objects, settings, client=None)

    assert set(dirs) == {PurePosixPath("a"), PurePosixPath("a/b")}
    assert PurePosixPath("a/b/c.txt") in all_entries
    assert PurePosixPath("a/d.txt") in all_entries


def test_build_tree_links_children_to_parents(settings):
    objects = [make_object("a/b.txt")]

    dirs, all_entries = build_tree(objects, settings, client=None)

    a_dir = dirs[PurePosixPath("a")]
    assert [c.path for c in a_dir.children] == [PurePosixPath("a/b.txt")]


def test_build_tree_skips_index_and_bzempty_files(settings):
    objects = [make_object("a/index.html"), make_object("a/.bzEmpty"), make_object("a/real.txt")]

    _, all_entries = build_tree(objects, settings, client=None)

    assert PurePosixPath("a/index.html") not in all_entries
    assert PurePosixPath("a/.bzEmpty") not in all_entries
    assert PurePosixPath("a/real.txt") in all_entries


def test_resolve_content_types_uses_extension_fast_path_without_network():
    obj = S3Object(path=PurePosixPath("a.txt"), name="a.txt", parent=PurePosixPath("."), _client=None)

    resolve_content_types([obj])

    assert obj.content_type == "text/plain"


def test_resolve_content_types_falls_back_to_sniff_for_unknown_extensions():
    client = MagicMock()
    client.get_object.return_value.read.return_value = b"hello world"
    obj = S3Object(
        path=PurePosixPath("a.weirdext"),
        name="a.weirdext",
        parent=PurePosixPath("."),
        _client=client,
        _bucket_name="test-bucket",
    )

    resolve_content_types([obj])

    assert obj.content_type is not None
    assert obj.content_type != "unknown"


def test_resolve_content_types_skips_directories():
    dir_obj = S3Object(path=PurePosixPath("d"), name="d", parent=PurePosixPath("."), is_dir=True)

    resolve_content_types([dir_obj])

    assert dir_obj.content_type is None


def test_resolve_content_types_reports_progress_once_per_file():
    objs = [S3Object(path=PurePosixPath(f"{i}.txt"), name=f"{i}.txt", parent=PurePosixPath(".")) for i in range(3)]
    calls = []

    resolve_content_types(objs, on_progress=lambda: calls.append(1))

    assert len(calls) == 3


def test_resolve_content_types_reports_progress_for_sniffed_files_too():
    client = MagicMock()
    client.get_object.return_value.read.return_value = b"hello world"
    obj = S3Object(
        path=PurePosixPath("a.weirdext"),
        name="a.weirdext",
        parent=PurePosixPath("."),
        _client=client,
        _bucket_name="test-bucket",
    )
    calls = []

    resolve_content_types([obj], on_progress=lambda: calls.append(1))

    assert len(calls) == 1


def test_sniff_content_type_returns_unknown_without_a_client():
    obj = S3Object(path=PurePosixPath("a.weirdext"), name="a.weirdext", parent=PurePosixPath("."), _client=None)

    assert _sniff_content_type(obj, MagicMock()) == "unknown"


def test_sniff_content_type_returns_unknown_on_fetch_error():
    client = MagicMock()
    obj = S3Object(
        path=PurePosixPath("a.weirdext"),
        name="a.weirdext",
        parent=PurePosixPath("."),
        _client=client,
        _bucket_name="test-bucket",
    )

    with patch(
        "s3index.models.fetch_prefix_bytes",
        side_effect=S3Error("AccessDenied", "not entitled", None, None, None, MagicMock()),
    ):
        assert _sniff_content_type(obj, MagicMock()) == "unknown"
