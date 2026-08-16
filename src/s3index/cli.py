"""Orchestrates listing S3 objects and generating directory-index pages."""

from pathlib import PurePosixPath

from minio import Minio

from s3index.models import S3Object, build_tree
from s3index.render import build_environment, render_directory
from s3index.settings import Settings
from s3index.storage import list_all_objects


def main() -> None:
    settings = Settings()  # type: ignore

    client = Minio(
        str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    env = build_environment()
    template = env.get_template(settings.template or "default.html")

    print("Listing S3 objects...")
    all_objects = list_all_objects(client, settings.s3_bucket_name, settings.s3_bucket_prefix)

    dirs, all_entries = build_tree(all_objects, settings, client)

    print("Computing directory sizes...")
    for dir_obj in dirs.values():
        dir_obj.compute_totals()

    for obj in sorted(dirs.values(), key=lambda x: str(x.path)):
        render_directory(obj, template, settings, client)

    if settings.s3_bucket_prefix:
        try:
            root_dir = dirs[PurePosixPath(settings.s3_bucket_prefix)]
        except KeyError as e:
            raise e
    else:
        root_dir = S3Object(PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
        root_dir.children = [x for x in all_entries.values() if x.parent == PurePosixPath(".")]
        _ = root_dir.compute_totals()

    render_directory(root_dir, template, settings, client)

    print("All directory indexes generated successfully.")


if __name__ == "__main__":
    main()
