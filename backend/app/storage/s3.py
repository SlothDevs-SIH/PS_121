"""S3-compatible object storage client (SeaweedFS in compose; MinIO/AWS S3/Ceph also work)."""

from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@lru_cache
def get_s3_client() -> "S3Client":
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=settings.readiness_timeout_s,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )


def bucket_exists(client: "S3Client", bucket: str) -> bool:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchBucket", "NotFound"}:
            return False
        raise
    return True


def ensure_buckets(client: "S3Client", buckets: list[str]) -> list[str]:
    """Create any missing buckets; returns the names that were created."""
    created = []
    for bucket in buckets:
        if not bucket_exists(client, bucket):
            client.create_bucket(Bucket=bucket)
            created.append(bucket)
    return created
