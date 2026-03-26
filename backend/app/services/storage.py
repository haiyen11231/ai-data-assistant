from __future__ import annotations
import io
import os
import uuid

import boto3
from botocore.exceptions import ClientError

_BUCKET    = os.environ.get("AI_BUCKET", "ai-data-assistant")
_REGION    = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
_ENDPOINT  = os.environ.get("S3_ENDPOINT_URL")   # None → use real AWS

def _client():
    kwargs = dict(
        region_name=_REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    if _ENDPOINT:
        kwargs["endpoint_url"] = _ENDPOINT 
    return boto3.client("s3", **kwargs)


def ensure_bucket() -> None:
    s3 = _client()
    try:
        s3.head_bucket(Bucket=_BUCKET)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            if _REGION == "us-east-1":
                s3.create_bucket(Bucket=_BUCKET)
            else:
                s3.create_bucket(
                    Bucket=_BUCKET,
                    CreateBucketConfiguration={"LocationConstraint": _REGION},
                )
        else:
            raise


def upload_file(
    file_bytes: bytes,
    session_id: str,
    dataset_id: str,
    filename: str,
) -> str:
    key = f"uploads/{session_id}/{dataset_id}/{filename}"
    _client().put_object(
        Bucket=_BUCKET,
        Key=key,
        Body=file_bytes,
        Tagging=f"session_id={session_id}",
    )
    return key


def download_file(s3_key: str) -> bytes:
    response = _client().get_object(Bucket=_BUCKET, Key=s3_key)
    return response["Body"].read()


def delete_file(s3_key: str) -> None:
    try:
        _client().delete_object(Bucket=_BUCKET, Key=s3_key)
    except ClientError:
        pass


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )
