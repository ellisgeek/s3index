"""Tests for the render_all orchestration and main entrypoint in cli.py."""

from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
import typer
from conftest import make_object
from minio.error import S3Error
from pydantic import BaseModel, ValidationError

from s3index.cli import main, render_all, summarize_results
from s3index.models import S3Object
from s3index.render import RenderResult, build_environment


@pytest.fixture
def template():
    return build_environment().get_template("default.html")


def make_dirs(n: int) -> list[S3Object]:
    return [S3Object(path=PurePosixPath(f"d{i}"), name=f"d{i}", parent=PurePosixPath("."), is_dir=True) for i in range(n)]


class _RequiredField(BaseModel):
    required: str


class _TypedField(BaseModel):
    number: int


def missing_settings_error() -> ValidationError:
    try:
        _RequiredField.model_validate({})
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


def invalid_settings_error() -> ValidationError:
    try:
        _TypedField(number="not-a-number")
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


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


def test_main_errors_when_dry_run_and_output_dir_together(tmp_path):
    with pytest.raises(typer.Exit) as exc_info:
        main(dry_run=True, output_dir=tmp_path)

    assert exc_info.value.exit_code == 1


def test_main_errors_on_missing_required_settings():
    with patch("s3index.cli.Settings", side_effect=missing_settings_error()), pytest.raises(typer.Exit) as exc_info:
        main()

    assert exc_info.value.exit_code == 1


def test_main_errors_on_invalid_settings():
    with patch("s3index.cli.Settings", side_effect=invalid_settings_error()), pytest.raises(typer.Exit) as exc_info:
        main()

    assert exc_info.value.exit_code == 1


def test_main_errors_when_listing_fails(settings):
    error = S3Error("AccessDenied", "not entitled", None, None, None, MagicMock())
    with (
        patch("s3index.cli.Settings", return_value=settings),
        patch("s3index.cli.Minio"),
        patch("s3index.cli.list_all_objects", side_effect=error),
        pytest.raises(typer.Exit) as exc_info,
    ):
        main()

    assert exc_info.value.exit_code == 2


def test_main_errors_when_configured_prefix_is_not_found(settings):
    settings.s3_bucket_prefix = "missing-prefix"
    with (
        patch("s3index.cli.Settings", return_value=settings),
        patch("s3index.cli.Minio"),
        patch("s3index.cli.list_all_objects", return_value=[make_object("other/a.txt")]),
        pytest.raises(typer.Exit) as exc_info,
    ):
        main()

    assert exc_info.value.exit_code == 2


def test_main_dry_run_reports_indexes_for_the_root_and_every_directory(settings, capsys):
    with (
        patch("s3index.cli.Settings", return_value=settings),
        patch("s3index.cli.Minio"),
        patch("s3index.cli.list_all_objects", return_value=[make_object("a.txt"), make_object("dir/b.txt")]),
    ):
        main(dry_run=True)

    assert "Would write 2 indexes." in capsys.readouterr().out


def test_main_renders_with_a_configured_prefix_and_applies_overrides(settings, tmp_path):
    settings.s3_bucket_prefix = "root"
    with (
        patch("s3index.cli.Settings", return_value=settings),
        patch("s3index.cli.Minio"),
        patch("s3index.cli.list_all_objects", return_value=[make_object("root/a.txt")]),
    ):
        main(output_dir=tmp_path, s3_bucket_name="overridden-bucket")

    assert settings.s3_bucket_name == "overridden-bucket"
    assert (tmp_path / "index.html").exists()
