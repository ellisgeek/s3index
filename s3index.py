from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Optional

from humanize import naturalsize
from jinja2 import Environment, PackageLoader, select_autoescape
from minio import Minio
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from yarl import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    s3_endpoint: str = Field()
    s3_bucket_name: str = Field()
    s3_access_key: str = Field()
    s3_secret_key: str = Field()
    s3_scheme: str = Field(default="https")
    template: Optional[str] = Field(default=None)
    index_name: str = Field(default="index.html")


def main():
    settings = Settings()

    @dataclass
    class S3Object:
        def __init__(self, obj):
            self.path = PurePosixPath(obj.object_name)
            self.name = self.path.name
            self.parent = self.path.parent
            self.bytes = obj.size
            self.size = naturalsize(self.bytes)
            self.tags = obj.tags
            self.last_modified = obj.last_modified
            self.content_type = obj.content_type
            s3url = URL(f"{settings.s3_scheme}://{settings.s3_endpoint}")
            self.s3url = s3url / settings.s3_bucket_name / str(self.path)

    client = Minio(
        str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    env = Environment(
        loader=PackageLoader("s3index"),
        autoescape=select_autoescape(),
    )

    # List objects information recursively.
    objects = client.list_objects(settings.s3_bucket_name, recursive=True)

    jinja_objects = []

    for obj in objects:
        s3obj = S3Object(obj)
        if s3obj.name != ".bzEmpty" and s3obj.path != settings.index_name:
            jinja_objects.append(s3obj)

    env.globals = {
        "endpoint": settings.s3_endpoint,
        "bucket_name": settings.s3_bucket_name,
        "objects": jinja_objects,
    }

    template = env.get_template(settings.template or "default.html")

    html = template.render()
    raw = BytesIO(html.encode())

    client.put_object(
        settings.s3_bucket_name,
        settings.index_name,
        raw,
        length=len(raw.getvalue()),
        content_type="text/html",
    )

    index = S3Object(client.stat_object(settings.s3_bucket_name, settings.index_name))

    print(index.s3url)


if __name__ == "__main__":
    main()
