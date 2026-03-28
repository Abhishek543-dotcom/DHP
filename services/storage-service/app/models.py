from typing import Optional
from pydantic import BaseModel, Field


class BucketCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")

    class Config:
        json_schema_extra = {
            "example": {"name": "my-data-bucket"}
        }


class BucketResponse(BaseModel):
    name: str
    status: str
    creation_date: Optional[str] = None


class BucketListResponse(BaseModel):
    total: int
    buckets: list[dict]


class ObjectListResponse(BaseModel):
    bucket: str
    prefix: str
    objects: list[dict]
    total: int
    is_truncated: bool = False
    next_continuation_token: Optional[str] = None


class PresignedUrlRequest(BaseModel):
    object_key: str = Field(..., description="S3 object key")
    operation: str = Field(default="download", description="'upload' or 'download'")
    expiry: Optional[int] = Field(None, description="URL expiry in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "object_key": "data/sales/2026/03/transactions.parquet",
                "operation": "download",
                "expiry": 3600,
            }
        }


class PresignedUrlResponse(BaseModel):
    bucket: str
    object_key: str
    operation: str
    url: str
    expiry: int

