"""Tests for the render_all orchestration in cli.py."""

from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
import typer
from minio.error import S3Error

from s3index.cli import render_all, summarize_results
from s3index.models import S3Object
from s3index.render import RenderResult, build_environment


@pytest.fixture
def template():
    return build_environment().get_template("default.html")


def make_dirs(n: int) -> list[S3Object]:
    return [S3Object(path=PurePosixPath(f"d{i}"), name=f"d{i}", parent=PurePosixPath("."), is_dir=True) for i in range(n)]


def test_render_all_exits_with_s3_error_code_on_a_failed_upload(settings, template):
    dirs = make_dirs(5)

    def flaky_upload(client, bucket_name, object_name, html):
        if "d2" in object_name:
            raise S3Error("AccessDenied", "not entitled", None, None, None, MagicMock())

    with patch("s3index.render.upload_index", side_effect=flaky_upload):
        with pytest.raises(typer.Exit) as exc_info:
            render_all(dirs, template, settings, client=MagicMock(), dry_run=False, output_dir=None)

    assert exc_info.value.exit_code == 2


def test_render_all_uploads_every_directory_when_none_fail(settings, template):
    dirs = make_dirs(5)

    with patch("s3index.render.upload_index") as mock_upload:
        results = render_all(dirs, template, settings, client=MagicMock(), dry_run=False, output_dir=None)

    assert mock_upload.call_count == 5
    assert results == [RenderResult.UPLOADED] * 5


def test_summarize_results_reports_dry_run():
    assert summarize_results([RenderResult.DRY_RUN] * 3) == "Would write 3 indexes."


def test_summarize_results_reports_local_write():
    assert summarize_results([RenderResult.WRITTEN] * 4) == "Wrote 4 indexes."


def test_summarize_results_reports_uploaded_and_skipped_counts():
    results = [RenderResult.UPLOADED] * 2 + [RenderResult.SKIPPED] * 3
    assert summarize_results(results) == "Uploaded 2 indexes, skipped 3 unchanged."
