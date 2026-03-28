import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Client:
    """Wrapper around boto3 S3 client for MinIO/S3 operations."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    def create_bucket(self, bucket_name: str) -> dict:
        """Create a new S3 bucket."""
        try:
            self.client.create_bucket(Bucket=bucket_name)
            logger.info(f"Created bucket: {bucket_name}")
            return {"bucket": bucket_name, "status": "created"}
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                return {"bucket": bucket_name, "status": "already_exists"}
            raise

    def list_buckets(self) -> list[dict]:
        """List all buckets."""
        response = self.client.list_buckets()
        return [
            {
                "name": b["Name"],
                "creation_date": b["CreationDate"].isoformat(),
            }
            for b in response.get("Buckets", [])
        ]

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = "",
        max_keys: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> dict:
        """List objects in a bucket with optional prefix."""
        params = {
            "Bucket": bucket_name,
            "Prefix": prefix,
            "MaxKeys": max_keys,
        }
        if continuation_token:
            params["ContinuationToken"] = continuation_token

        try:
            response = self.client.list_objects_v2(**params)
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
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucket":
                return None
            raise

    def generate_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        operation: str = "get_object",
        expiry: int = None,
    ) -> str:
        """Generate a presigned URL for upload or download."""
        if expiry is None:
            expiry = settings.presigned_url_expiry

        client_method = "get_object" if operation == "download" else "put_object"

        url = self.client.generate_presigned_url(
            ClientMethod=client_method,
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiry,
        )
        return url

    def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """Delete an object from a bucket."""
        try:
            self.client.delete_object(Bucket=bucket_name, Key=object_key)
            logger.info(f"Deleted object: s3://{bucket_name}/{object_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete object: {e}")
            return False

    def ensure_prefix(self, bucket_name: str, prefix: str):
        """Ensure a prefix (directory) exists by creating a placeholder."""
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

