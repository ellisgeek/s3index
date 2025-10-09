from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import Dict, List, Optional

from humanize import naturalsize
from jinja2 import Environment, PackageLoader, select_autoescape
from magika import Magika
from minio import Minio
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from yarl import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    s3_endpoint: str = Field()
    s3_bucket_name: str = Field()
    s3_bucket_prefix: str = Field(default="")
    s3_access_key: str = Field()
    s3_secret_key: str = Field()
    s3_scheme: str = Field(default="https")
    template: Optional[str] = Field(default=None)
    index_name: str = Field(default="index.html")


def main():
    settings = Settings()

    client = Minio(
        str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    env = Environment(
        loader=PackageLoader("s3index"),
        autoescape=select_autoescape(),
    )


    @dataclass
    class S3Object:
        path: PurePosixPath
        name: str
        parent: PurePosixPath
        bytes: int = 0
        size: str = "0 B"
        last_modified: Optional[datetime] = None
        s3url: Optional[URL] = None
        is_dir: bool = False
        children: List["S3Object"] = field(default_factory=list)
        _content_type: Optional[str] = field(default=None, init=False, repr=False)
        total_bytes: int = 0
        total_size: str = "0 B"

        @classmethod
        def from_minio(cls, obj):
            path = PurePosixPath(obj.object_name)
            s3url = URL(f"{settings.s3_scheme}://{settings.s3_endpoint}") / settings.s3_bucket_name / str(path)
            return cls(
                path=path,
                name=path.name or "/",
                parent=path.parent,
                bytes=obj.size,
                size=naturalsize(obj.size),
                last_modified=obj.last_modified,
                s3url=s3url,
                is_dir=False,
            )

        @property
        def relpath(self):
            prefix = PurePosixPath(settings.s3_bucket_prefix)
            return self.path.relative_to(prefix) if settings.s3_bucket_prefix else self.path

        @property
        def link(self):
            return f"{self.name}/index.html" if self.is_dir else self.name

        @property
        def content_type(self):
            if self.is_dir:
                return "directory"
            if self._content_type:
                return self._content_type

            try:
                response = client.get_object(
                    settings.s3_bucket_name,
                    str(self.path),
                    offset=0,
                    length=2048,
                )
                data = response.read()
                response.close()
                response.release_conn()
                m = Magika()
                result = m.identify_bytes(data)
                self._content_type = result.output.mime_type if result and result.output else "application/octet-stream"
            except Exception:
                self._content_type = "unknown"
            return self._content_type

        def compute_totals(self) -> int:
            """Recursively compute total bytes for this object and its children."""
            if not self.is_dir:
                self.total_bytes = self.bytes
            else:
                self.total_bytes = sum(child.compute_totals() for child in self.children)
            self.total_size = naturalsize(self.total_bytes)
            return self.total_bytes

    print("Listing S3 objects...")
    all_objects = list(client.list_objects(settings.s3_bucket_name, settings.s3_bucket_prefix, recursive=True))

    # Map paths to S3Objects
    objects_by_path: Dict[PurePosixPath, S3Object] = {}

    for obj in all_objects:
        s3obj = S3Object.from_minio(obj)
        if s3obj.name in {".bzEmpty", settings.index_name}:
            continue
        objects_by_path[s3obj.path] = s3obj

    # Add virtual directories
    dirs: Dict[PurePosixPath, S3Object] = {}
    for path in list(objects_by_path.keys()):
        for parent in path.parents:
            if parent == PurePosixPath("."):
                continue
            if parent not in dirs:
                dirs[parent] = S3Object(
                    path=parent,
                    name=parent.name or "/",
                    parent=parent.parent,
                    is_dir=True,
                )

    # Merge all objects
    all_entries = {**objects_by_path, **dirs}

    # Build tree structure
    for obj in all_entries.values():
        if obj.parent in all_entries:
            all_entries[obj.parent].children.append(obj)

    # Compute directory sizes
    print("Computing directory sizes...")
    for dir_obj in dirs.values():
        dir_obj.compute_totals()

    template = env.get_template(settings.template or "default.html")

    def render_directory(dir_obj: S3Object):
        """Render and upload an index for this directory."""
        objects = sorted(dir_obj.children, key=lambda x: (not x.is_dir, x.name.lower()))

        # Determine if this directory is the logical root
        is_root = str(dir_obj.path).rstrip("/") == str(settings.s3_bucket_prefix).rstrip("/") or str(dir_obj.path) == "."

        parent_link = None if is_root else "../index.html"

        html = template.render(
            objects=objects,
            current_dir=dir_obj.path if not is_root else "/",
            parent_link=parent_link,
            bucket_name=settings.s3_bucket_name,
            endpoint=settings.s3_endpoint,
            bucket_prefix=settings.s3_bucket_prefix,
            total_bytes=dir_obj.total_bytes,
            total_size=dir_obj.total_size,
        )

        raw = BytesIO(html.encode())
        index_path = (
            f"{dir_obj.path}/{settings.index_name}"
            if not is_root
            else settings.index_name
        )

        print(f"Uploading index for {dir_obj.path or '/'} → {index_path}")

        client.put_object(
            settings.s3_bucket_name,
            str(index_path),
            raw,
            length=len(raw.getvalue()),
            content_type="text/html",
        )

    # Generate indexes recursively
    for obj in sorted(dirs.values(), key=lambda x: str(x.path)):
        render_directory(obj)

    # Root directory
    if settings.s3_bucket_prefix:
        root_dir = dirs.get(PurePosixPath(settings.s3_bucket_prefix))
    else:
        root_dir = S3Object(PurePosixPath("."), name="/", parent=PurePosixPath(""), is_dir=True)
        root_dir.children = [x for x in all_entries.values() if x.parent == PurePosixPath(".")]
        root_dir.compute_totals()

    render_directory(root_dir)

    print("All directory indexes generated successfully.")


if __name__ == "__main__":
    main()
