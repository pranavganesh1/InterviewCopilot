import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

RESUME_BUCKET = "resumes"


def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket(s3: BaseClient, bucket: str) -> None:
    """Create the bucket if missing; safe to call on every request.

    Note: SeaweedFS's ListBuckets is unreliable in 4.50, so availability is
    checked with head_bucket, and a raced create is treated as success.
    """
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            s3.create_bucket(Bucket=bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                raise
