"""Typed configuration for s3index, loaded from `.env`/environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    s3_endpoint: str = Field()
    s3_bucket_name: str = Field(default="")
    s3_bucket_prefix: str = Field(default="")
    s3_access_key: str = Field()
    s3_secret_key: str = Field()
    s3_scheme: str = Field(default="https")
    template: str | None = Field(default=None)
    index_name: str = Field(default="index.html")
