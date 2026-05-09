import logging
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_boto_client():
    """Construct an S3 boto3 client.

    When `s3_endpoint` is set (local MinIO), use static credentials and
    path-style addressing. Otherwise (AWS), let boto3 resolve credentials
    via the standard chain (env -> task role -> instance profile).
    """
    kwargs = {"region_name": settings.s3_region}
    if settings.s3_endpoint:
        kwargs["endpoint_url"] = settings.s3_endpoint
    if settings.s3_access_key and settings.s3_secret_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key
        kwargs["aws_secret_access_key"] = settings.s3_secret_key

    config_args = {"retries": {"max_attempts": 5, "mode": "standard"}}
    if settings.s3_force_path_style or settings.s3_endpoint:
        # MinIO and many third-party S3 implementations only support path-style.
        config_args["s3"] = {"addressing_style": "path"}
    kwargs["config"] = BotoConfig(**config_args)

    return boto3.client("s3", **kwargs)


class S3Client:
    """Wrapper around boto3 S3 client for AWS S3 / MinIO operations."""

    def __init__(self):
        self.client = _build_boto_client()

    def create_bucket(self, bucket_name: str) -> dict:
        """Create a new S3 bucket. Region must be passed for non-us-east-1."""
        try:
            kwargs = {"Bucket": bucket_name}
            if settings.s3_region and settings.s3_region != "us-east-1" and not settings.s3_endpoint:
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
            self.client.create_bucket(**kwargs)
            logger.info("Created bucket: %s", bucket_name)
            return {"bucket": bucket_name, "status": "created"}
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                return {"bucket": bucket_name, "status": "already_exists"}
            raise

    def list_buckets(self) -> list[dict]:
        response = self.client.list_buckets()
        return [
            {"name": b["Name"], "creation_date": b["CreationDate"].isoformat()}
            for b in response.get("Buckets", [])
        ]

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = "",
        max_keys: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> Optional[dict]:
        params = {"Bucket": bucket_name, "Prefix": prefix, "MaxKeys": max_keys}
        if continuation_token:
            params["ContinuationToken"] = continuation_token
        try:
            response = self.client.list_objects_v2(**params)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucket":
                return None
            raise

        objects = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
                "etag": obj.get("ETag", ""),
            }
            for obj in response.get("Contents", [])
        ]
        return {
            "bucket": bucket_name,
            "prefix": prefix,
            "objects": objects,
            "total": len(objects),
            "is_truncated": response.get("IsTruncated", False),
            "next_continuation_token": response.get("NextContinuationToken"),
        }

    def generate_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        operation: str = "get_object",
        expiry: Optional[int] = None,
    ) -> str:
        if expiry is None:
            expiry = settings.presigned_url_expiry
        client_method = "get_object" if operation == "download" else "put_object"
        return self.client.generate_presigned_url(
            ClientMethod=client_method,
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiry,
        )

    def delete_object(self, bucket_name: str, object_key: str) -> bool:
        try:
            self.client.delete_object(Bucket=bucket_name, Key=object_key)
            logger.info("Deleted object: s3://%s/%s", bucket_name, object_key)
            return True
        except ClientError as e:
            logger.error("Failed to delete object: %s", e)
            return False

    def ensure_prefix(self, bucket_name: str, prefix: str) -> None:
        if not prefix.endswith("/"):
            prefix += "/"
        try:
            self.client.put_object(Bucket=bucket_name, Key=prefix, Body=b"")
        except ClientError:
            pass


_s3_client: Optional[S3Client] = None


def get_s3_client() -> S3Client:
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
    return _s3_client
