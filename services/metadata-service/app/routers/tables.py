import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import (
    TableCreateRequest,
    TableUpdateRequest,
    TableResponse,
    TableListResponse,
    SnapshotListResponse,
)
from app.security import require_api_key
from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/databases/{db_name}/tables",
    tags=["Tables"],
    dependencies=[Depends(require_api_key)],
)


def get_metadata_service(db: AsyncSession = Depends(get_db)) -> MetadataService:
    return MetadataService(db)


@router.post("/", response_model=TableResponse, status_code=201)
async def create_table(
    db_name: str,
    request: TableCreateRequest,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Create a new table in a database."""
    table = await svc.create_table(db_name, request)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")
    return table


@router.get("/", response_model=TableListResponse)
async def list_tables(
    db_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """List all tables in a database."""
    result = await svc.list_tables(db_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")
    return result


@router.get("/{table_name}", response_model=TableResponse)
async def get_table(
    db_name: str,
    table_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Get table details including schema, partitions, and properties."""
    table = await svc.get_table(db_name, table_name)
    if not table:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{db_name}.{table_name}' not found",
        )
    return table


@router.put("/{table_name}", response_model=TableResponse)
async def update_table(
    db_name: str,
    table_name: str,
    request: TableUpdateRequest,
    svc: MetadataService = Depends(get_metadata_service),
):
    """
    Update table schema (schema evolution) or properties.

    Supports adding columns, dropping columns, renaming columns,
    and updating properties/description.
    """
    table = await svc.update_table(db_name, table_name, request)
    if not table:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{db_name}.{table_name}' not found",
        )
    return table


@router.delete("/{table_name}", status_code=204)
async def drop_table(
    db_name: str,
    table_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Drop a table."""
    dropped = await svc.drop_table(db_name, table_name)
    if not dropped:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{db_name}.{table_name}' not found",
        )


@router.get("/{table_name}/snapshots", response_model=SnapshotListResponse)
async def get_table_snapshots(
    db_name: str,
    table_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Get Iceberg snapshots for a table (time travel support)."""
    result = await svc.get_table_snapshots(db_name, table_name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{db_name}.{table_name}' not found",
        )
    return result

