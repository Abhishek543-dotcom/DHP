import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.models import CatalogDatabase, CatalogTable
from app.glue_client import get_glue_client
from app.models import (
    DatabaseCreateRequest,
    DatabaseResponse,
    DatabaseListResponse,
)
from app.security import require_api_key
from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/databases",
    tags=["Databases"],
    dependencies=[Depends(require_api_key)],
)


def get_metadata_service(db: AsyncSession = Depends(get_db)) -> MetadataService:
    return MetadataService(db)


@router.post("/", response_model=DatabaseResponse, status_code=201)
async def create_database(
    request: DatabaseCreateRequest,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Create a new database (namespace) in the lakehouse catalog."""
    try:
        return await svc.create_database(request)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Database '{request.db_name}' already exists",
            )
        raise


@router.get("/", response_model=DatabaseListResponse)
async def list_databases(
    svc: MetadataService = Depends(get_metadata_service),
):
    """List all databases in the catalog."""
    return await svc.list_databases()


@router.get("/{db_name}", response_model=DatabaseResponse)
async def get_database(
    db_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Get database details by name."""
    db = await svc.get_database(db_name)
    if not db:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")
    return db


@router.delete("/{db_name}", status_code=204)
async def drop_database(
    db_name: str,
    svc: MetadataService = Depends(get_metadata_service),
):
    """Drop a database and all its tables."""
    dropped = await svc.drop_database(db_name)
    if not dropped:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")


@router.post("/{db_name}/sync-glue")
async def sync_glue(
    db_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Backfill all tables in this DHP database into AWS Glue.

    Idempotent: tables already registered in Glue produce ``outcome=exists``
    counter increments and are skipped. Returns per-table results.
    """
    glue = get_glue_client()
    if not glue.enabled:
        raise HTTPException(
            status_code=400,
            detail="Glue write-through is not configured (GLUE_CATALOG_DATABASE empty)",
        )

    db_record = (
        await db.execute(select(CatalogDatabase).where(CatalogDatabase.db_name == db_name))
    ).scalar_one_or_none()
    if not db_record:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")

    tables = (
        await db.execute(select(CatalogTable).where(CatalogTable.db_id == db_record.db_id))
    ).scalars().all()

    results = []
    for tbl in tables:
        # register_table is fully synchronous and swallows AWS errors as
        # warnings; we still report the attempt outcome here for the caller.
        glue.register_table(
            table_name=f"{db_name}__{tbl.table_name}",
            location=tbl.location,
        )
        results.append({"table": tbl.table_name, "submitted": True})

    return {"database": db_name, "table_count": len(results), "results": results}

