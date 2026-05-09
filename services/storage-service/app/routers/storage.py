import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.metrics import STORAGE_BUCKET_OPS_TOTAL, STORAGE_PRESIGNED_URLS_TOTAL
from app.models import (
    BucketCreateRequest,
    BucketResponse,
    BucketListResponse,
    ObjectListResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
)
from app.security import require_api_key
from app.s3_client import S3Client, get_s3_client

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(
    prefix="/api/v1/storage",
    tags=["Storage"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/buckets", response_model=BucketResponse, status_code=201)
async def create_bucket(
    request: BucketCreateRequest,
    s3: S3Client = Depends(get_s3_client),
):
    """Create a new storage bucket."""
    try:
        result = s3.create_bucket(request.name)
        STORAGE_BUCKET_OPS_TOTAL.labels(op="create", outcome="success").inc()
        return BucketResponse(name=request.name, status=result["status"])
    except Exception as e:
        STORAGE_BUCKET_OPS_TOTAL.labels(op="create", outcome="error").inc()
        raise HTTPException(status_code=500, detail=f"Failed to create bucket: {str(e)}")


@router.get("/buckets", response_model=BucketListResponse)
async def list_buckets(
    s3: S3Client = Depends(get_s3_client),
):
    """List all storage buckets."""
    buckets = s3.list_buckets()
    STORAGE_BUCKET_OPS_TOTAL.labels(op="list", outcome="success").inc()
    return BucketListResponse(total=len(buckets), buckets=buckets)


@router.get("/buckets/{bucket_name}/objects", response_model=ObjectListResponse)
async def list_objects(
    bucket_name: str,
    prefix: str = Query("", description="Object key prefix filter"),
    max_keys: int = Query(1000, ge=1, le=10000),
    continuation_token: str = Query(None, description="Pagination token"),
    s3: S3Client = Depends(get_s3_client),
):
    """List objects in a bucket with optional prefix filter."""
    result = s3.list_objects(
        bucket_name=bucket_name,
        prefix=prefix,
        max_keys=max_keys,
        continuation_token=continuation_token,
    )
    if result is None:
        STORAGE_BUCKET_OPS_TOTAL.labels(op="list_objects", outcome="not_found").inc()
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' not found")
    STORAGE_BUCKET_OPS_TOTAL.labels(op="list_objects", outcome="success").inc()
    return ObjectListResponse(**result)


@router.post("/buckets/{bucket_name}/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    bucket_name: str,
    request: PresignedUrlRequest,
    s3: S3Client = Depends(get_s3_client),
):
    """Generate a presigned URL for uploading or downloading objects."""
    expiry = request.expiry or settings.presigned_url_expiry
    try:
        url = s3.generate_presigned_url(
            bucket_name=bucket_name,
            object_key=request.object_key,
            operation=request.operation,
            expiry=expiry,
        )
        STORAGE_PRESIGNED_URLS_TOTAL.labels(operation=request.operation).inc()
        return PresignedUrlResponse(
            bucket=bucket_name,
            object_key=request.object_key,
            operation=request.operation,
            url=url,
            expiry=expiry,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")


@router.delete("/buckets/{bucket_name}/objects/{object_key:path}", status_code=204)
async def delete_object(
    bucket_name: str,
    object_key: str,
    s3: S3Client = Depends(get_s3_client),
):
    """Delete an object from a bucket."""
    success = s3.delete_object(bucket_name, object_key)
    if not success:
        STORAGE_BUCKET_OPS_TOTAL.labels(op="delete_object", outcome="error").inc()
        raise HTTPException(status_code=500, detail="Failed to delete object")
    STORAGE_BUCKET_OPS_TOTAL.labels(op="delete_object", outcome="success").inc()

