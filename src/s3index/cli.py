"""Orchestrates listing S3 objects and generating directory-index pages."""

import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import PurePosixPath

from jinja2 import Template
from minio import Minio
from minio.error import MinioException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from s3index.models import S3Object, build_tree, resolve_content_types
from s3index.render import EXIT_S3_ERROR, build_environment, render_directory
from s3index.settings import Settings
from s3index.storage import list_all_objects

EXIT_CONFIG_ERROR = 1


def render_all(dir_objs: Iterable[S3Object], template: Template, settings: Settings, client: Minio) -> None:
    """Render and upload each directory index concurrently.

    Stops scheduling new uploads as soon as one fails, and re-raises that
    failure's SystemExit from the main thread.
    """
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(render_directory, obj, template, settings, client): obj for obj in dir_objs}
        for future in as_completed(futures):
            try:
                future.result()
            except SystemExit:
                for f in futures:
                    f.cancel()
                raise


def main() -> None:
    try:
        settings = Settings()  # type: ignore
    except ValidationError as e:
        missing = [str(err["loc"][0]).upper() for err in e.errors() if err["type"] == "missing"]
        if missing:
            print(f"Error: missing config: {', '.join(missing)}", file=sys.stderr)
        else:
            print(f"Error: invalid config: {e}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_ERROR) from e

    client = Minio(
        str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    env = build_environment()
    template = env.get_template(settings.template or "default.html")

    print("Listing S3 objects...")
    try:
        all_objects = list_all_objects(client, settings.s3_bucket_name, settings.s3_bucket_prefix)
    except (MinioException, HTTPError) as e:
        print(f"Error: could not list objects in bucket '{settings.s3_bucket_name}': {e}", file=sys.stderr)
        raise SystemExit(EXIT_S3_ERROR) from e

    dirs, all_entries = build_tree(all_objects, settings, client)

    print("Resolving content types...")
    resolve_content_types(all_entries.values())

    print("Computing directory sizes...")
    for dir_obj in dirs.values():
        dir_obj.compute_totals()

    render_all(dirs.values(), template, settings, client)

    if settings.s3_bucket_prefix:
        try:
            root_dir = dirs[PurePosixPath(settings.s3_bucket_prefix)]
        except KeyError as e:
            print(
                f"Error: configured S3_BUCKET_PREFIX {settings.s3_bucket_prefix!r} "
                "not found among listed objects.",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_S3_ERROR) from e
    else:
        root_dir = S3Object(PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
        root_dir.children = [x for x in all_entries.values() if x.parent == PurePosixPath(".")]
        _ = root_dir.compute_totals()

    render_directory(root_dir, template, settings, client)

    print("All directory indexes generated successfully.")


if __name__ == "__main__":
    main()
