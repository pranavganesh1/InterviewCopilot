import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.core.config import get_settings
from app.core.logging import get_logger

RESUME_BUCKET = "resumes"
log = get_logger(__name__)


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
    Connection / misconfiguration failures propagate as ClientError or
    EndpointConnectionError for the caller to map to a 503.
    """
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", "") or "")
        # Missing bucket → create; other client errors → try create or re-raise.
        if code not in ("404", "NoSuchBucket", "NotFound", "403", "400"):
            # SeaweedFS often uses 404-like codes; still attempt create below.
            pass
    except (EndpointConnectionError, BotoCoreError, OSError):
        raise

    try:
        s3.create_bucket(Bucket=bucket)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", "") or "")
        if code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
            return
        log.warning(
            "s3_ensure_bucket_failed",
            bucket=bucket,
            error_class=code or type(exc).__name__,
        )
        raise
    except (EndpointConnectionError, BotoCoreError, OSError):
        log.warning(
            "s3_ensure_bucket_failed",
            bucket=bucket,
            error_class="connection",
        )
        raise
