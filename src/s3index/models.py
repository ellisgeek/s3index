"""S3Object dataclass and tree-building for the object listing."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

from humanize import naturalsize
from magika import Magika
from minio import Minio
from minio.datatypes import Object
from minio.error import MinioException
from urllib3.exceptions import HTTPError
from yarl import URL

from s3index.settings import Settings
from s3index.storage import fetch_prefix_bytes


@dataclass
class S3Object:
    path: PurePosixPath
    name: str
    parent: PurePosixPath
    bytes: int = 0
    size: str = "0 B"
    last_modified: datetime | None = None
    s3url: URL | None = None
    is_dir: bool = False
    children: list["S3Object"] = field(default_factory=list)
    total_bytes: int = 0
    total_size: str = "0 B"
    _client: Minio | None = field(default=None, repr=False, compare=False)
    _bucket_name: str = field(default="", repr=False, compare=False)
    _bucket_prefix: str = field(default="", repr=False, compare=False)
    _content_type: str | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_minio(cls, obj: Object, settings: Settings, client: Minio) -> "S3Object":
        """Build an S3Object from a minio listing entry."""
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
            _client=client,
            _bucket_name=settings.s3_bucket_name,
            _bucket_prefix=settings.s3_bucket_prefix,
        )

    @property
    def relpath(self) -> PurePosixPath:
        prefix = PurePosixPath(self._bucket_prefix)
        return self.path.relative_to(prefix) if self._bucket_prefix else self.path

    @property
    def link(self) -> str:
        return f"{self.name}/index.html" if self.is_dir else self.name

    @property
    def content_type(self) -> str:
        if self.is_dir:
            return "directory"
        if self._content_type:
            return self._content_type
        if self._client is None:
            self._content_type = "unknown"
            return self._content_type

        try:
            data = fetch_prefix_bytes(self._client, self._bucket_name, str(self.path))
            magika = Magika()
            result = magika.identify_bytes(data)
            self._content_type = result.output.mime_type if result and result.output else "application/octet-stream"
        except (MinioException, HTTPError):
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


def build_tree(
    all_objects: list[Object], settings: Settings, client: Minio
) -> tuple[dict[PurePosixPath, S3Object], dict[PurePosixPath, S3Object]]:
    """Build the object tree, including virtual directories, from a minio listing.

    Returns:
        A `(dirs, all_entries)` pair: `dirs` maps a directory path to its
        (virtual) S3Object, and `all_entries` maps every path (files and
        directories) to its S3Object, each with `children` populated.
    """
    objects_by_path: dict[PurePosixPath, S3Object] = {}
    for obj in all_objects:
        s3obj = S3Object.from_minio(obj, settings, client)
        if s3obj.name in {".bzEmpty", settings.index_name}:
            continue
        objects_by_path[s3obj.path] = s3obj

    dirs: dict[PurePosixPath, S3Object] = {}
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

    all_entries = {**objects_by_path, **dirs}
    for obj in all_entries.values():
        if obj.parent in all_entries:
            all_entries[obj.parent].children.append(obj)

    return dirs, all_entries
