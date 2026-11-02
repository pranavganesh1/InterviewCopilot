from app.db.s3 import RESUME_BUCKET, ensure_bucket, get_s3_client


def test_ensure_bucket_idempotent():
    s3 = get_s3_client()
    ensure_bucket(s3, RESUME_BUCKET)
    ensure_bucket(s3, RESUME_BUCKET)  # second call must not raise
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert RESUME_BUCKET in buckets
