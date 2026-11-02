from app.db.s3 import RESUME_BUCKET, ensure_bucket, get_s3_client


def test_ensure_bucket_idempotent():
    s3 = get_s3_client()
    ensure_bucket(s3, RESUME_BUCKET)
    ensure_bucket(s3, RESUME_BUCKET)  # raced re-create must not raise
    assert s3.head_bucket(Bucket=RESUME_BUCKET)["ResponseMetadata"]["HTTPStatusCode"] == 200

    # ListBuckets is unreliable on SeaweedFS 4.50; verify with object ops instead.
    s3.put_object(Bucket=RESUME_BUCKET, Key=".healthcheck", Body=b"ok")
    assert s3.get_object(Bucket=RESUME_BUCKET, Key=".healthcheck")["Body"].read() == b"ok"
