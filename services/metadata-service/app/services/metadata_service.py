import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import CatalogDatabase, CatalogTable, TableSnapshot, SchemaHistory
from app.models import (
    DatabaseCreateRequest,
    DatabaseResponse,
    DatabaseListResponse,
    TableCreateRequest,
    TableUpdateRequest,
    TableResponse,
    TableListResponse,
    SnapshotResponse,
    SnapshotListResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class MetadataService:
    """Business logic for catalog/metadata management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============================================
    # Database Operations
    # ============================================

    async def create_database(self, request: DatabaseCreateRequest) -> DatabaseResponse:
        """Create a new database namespace."""
        location = f"s3://{settings.s3_warehouse_bucket}/{request.db_name}/"

        db_record = CatalogDatabase(
            db_id=uuid4(),
            db_name=request.db_name,
            location=location,
            owner=request.owner,
            description=request.description,
            properties=request.properties,
        )

        self.db.add(db_record)
        await self.db.flush()

        logger.info(f"Created database: {request.db_name} at {location}")

        return DatabaseResponse(
            db_id=str(db_record.db_id),
            db_name=db_record.db_name,
            location=db_record.location,
            owner=db_record.owner,
            description=db_record.description,
            properties=db_record.properties,
            table_count=0,
            created_at=db_record.created_at,
            updated_at=db_record.updated_at,
        )

    async def get_database(self, db_name: str) -> Optional[DatabaseResponse]:
        """Get database by name."""
        result = await self.db.execute(
            select(CatalogDatabase).where(CatalogDatabase.db_name == db_name)
        )
        db_record = result.scalar_one_or_none()
        if not db_record:
            return None

        # Count tables
        count_result = await self.db.execute(
            select(func.count()).where(CatalogTable.db_id == db_record.db_id)
        )
        table_count = count_result.scalar() or 0

        return DatabaseResponse(
            db_id=str(db_record.db_id),
            db_name=db_record.db_name,
            location=db_record.location,
            owner=db_record.owner,
            description=db_record.description,
            properties=db_record.properties,
            table_count=table_count,
            created_at=db_record.created_at,
            updated_at=db_record.updated_at,
        )

    async def list_databases(self) -> DatabaseListResponse:
        """List all databases."""
        result = await self.db.execute(
            select(CatalogDatabase).order_by(CatalogDatabase.db_name)
        )
        databases = result.scalars().all()

        db_responses = []
        for db_record in databases:
            count_result = await self.db.execute(
                select(func.count()).where(CatalogTable.db_id == db_record.db_id)
            )
            table_count = count_result.scalar() or 0

            db_responses.append(
                DatabaseResponse(
                    db_id=str(db_record.db_id),
                    db_name=db_record.db_name,
                    location=db_record.location,
                    owner=db_record.owner,
                    description=db_record.description,
                    properties=db_record.properties,
                    table_count=table_count,
                    created_at=db_record.created_at,
                    updated_at=db_record.updated_at,
                )
            )

        return DatabaseListResponse(total=len(db_responses), databases=db_responses)

    async def drop_database(self, db_name: str) -> bool:
        """Drop a database and all its tables."""
        result = await self.db.execute(
            select(CatalogDatabase).where(CatalogDatabase.db_name == db_name)
        )
        db_record = result.scalar_one_or_none()
        if not db_record:
            return False

        await self.db.delete(db_record)
        await self.db.flush()
        logger.info(f"Dropped database: {db_name}")
        return True

    # ============================================
    # Table Operations
    # ============================================

    async def create_table(
        self, db_name: str, request: TableCreateRequest
    ) -> Optional[TableResponse]:
        """Create a new table in a database."""
        # Get database
        result = await self.db.execute(
            select(CatalogDatabase).where(CatalogDatabase.db_name == db_name)
        )
        db_record = result.scalar_one_or_none()
        if not db_record:
            return None

        location = f"{db_record.location}{request.table_name}/"

        # Build schema JSON
        schema_json = {
            "type": "struct",
            "fields": [
                {
                    "name": col.name,
                    "type": col.type,
                    "nullable": col.nullable,
                    "description": col.description,
                }
                for col in request.schema_fields
            ],
        }

        table_record = CatalogTable(
            table_id=uuid4(),
            db_id=db_record.db_id,
            table_name=request.table_name,
            table_type=request.table_type,
            location=location,
            schema_json=schema_json,
            partition_spec=request.partition_spec,
            sort_order=request.sort_order,
            properties=request.properties,
            description=request.description,
        )

        self.db.add(table_record)

        # Record initial schema version
        schema_record = SchemaHistory(
            table_id=table_record.table_id,
            version=1,
            schema_json=schema_json,
            change_summary="Initial schema creation",
        )
        self.db.add(schema_record)
        await self.db.flush()

        logger.info(f"Created table: {db_name}.{request.table_name} at {location}")

        return TableResponse(
            table_id=str(table_record.table_id),
            db_name=db_name,
            table_name=table_record.table_name,
            table_type=table_record.table_type,
            location=table_record.location,
            schema_json=table_record.schema_json,
            partition_spec=table_record.partition_spec,
            sort_order=table_record.sort_order,
            current_snapshot_id=table_record.current_snapshot_id,
            properties=table_record.properties,
            description=table_record.description,
            created_at=table_record.created_at,
            updated_at=table_record.updated_at,
        )

    async def get_table(self, db_name: str, table_name: str) -> Optional[TableResponse]:
        """Get table details."""
        result = await self.db.execute(
            select(CatalogTable)
            .join(CatalogDatabase)
            .where(CatalogDatabase.db_name == db_name)
            .where(CatalogTable.table_name == table_name)
        )
        table_record = result.scalar_one_or_none()
        if not table_record:
            return None

        return TableResponse(
            table_id=str(table_record.table_id),
            db_name=db_name,
            table_name=table_record.table_name,
            table_type=table_record.table_type,
            location=table_record.location,
            schema_json=table_record.schema_json,
            partition_spec=table_record.partition_spec,
            sort_order=table_record.sort_order,
            current_snapshot_id=table_record.current_snapshot_id,
            properties=table_record.properties,
            description=table_record.description,
            created_at=table_record.created_at,
            updated_at=table_record.updated_at,
        )

    async def list_tables(self, db_name: str) -> Optional[TableListResponse]:
        """List all tables in a database."""
        result = await self.db.execute(
            select(CatalogDatabase).where(CatalogDatabase.db_name == db_name)
        )
        db_record = result.scalar_one_or_none()
        if not db_record:
            return None

        result = await self.db.execute(
            select(CatalogTable)
            .where(CatalogTable.db_id == db_record.db_id)
            .order_by(CatalogTable.table_name)
        )
        tables = result.scalars().all()

        return TableListResponse(
            total=len(tables),
            db_name=db_name,
            tables=[
                TableResponse(
                    table_id=str(t.table_id),
                    db_name=db_name,
                    table_name=t.table_name,
                    table_type=t.table_type,
                    location=t.location,
                    schema_json=t.schema_json,
                    partition_spec=t.partition_spec,
                    sort_order=t.sort_order,
                    current_snapshot_id=t.current_snapshot_id,
                    properties=t.properties,
                    description=t.description,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                for t in tables
            ],
        )

    async def update_table(
        self, db_name: str, table_name: str, request: TableUpdateRequest
    ) -> Optional[TableResponse]:
        """Update table schema (schema evolution) or properties."""
        result = await self.db.execute(
            select(CatalogTable)
            .join(CatalogDatabase)
            .where(CatalogDatabase.db_name == db_name)
            .where(CatalogTable.table_name == table_name)
        )
        table_record = result.scalar_one_or_none()
        if not table_record:
            return None

        schema = table_record.schema_json.copy()
        fields = schema.get("fields", [])
        changes = []

        # Add columns
        for col in request.add_columns:
            fields.append({
                "name": col.name,
                "type": col.type,
                "nullable": col.nullable,
                "description": col.description,
            })
            changes.append(f"Added column: {col.name} ({col.type})")

        # Drop columns
        for col_name in request.drop_columns:
            fields = [f for f in fields if f["name"] != col_name]
            changes.append(f"Dropped column: {col_name}")

        # Rename columns
        for old_name, new_name in request.rename_columns.items():
            for f in fields:
                if f["name"] == old_name:
                    f["name"] = new_name
                    changes.append(f"Renamed column: {old_name} -> {new_name}")
                    break

        schema["fields"] = fields
        table_record.schema_json = schema

        if request.properties is not None:
            table_record.properties = {**table_record.properties, **request.properties}

        if request.description is not None:
            table_record.description = request.description

        # Record schema change
        if changes:
            # Get latest version
            version_result = await self.db.execute(
                select(func.max(SchemaHistory.version)).where(
                    SchemaHistory.table_id == table_record.table_id
                )
            )
            latest_version = version_result.scalar() or 0

            schema_record = SchemaHistory(
                table_id=table_record.table_id,
                version=latest_version + 1,
                schema_json=schema,
                change_summary="; ".join(changes),
                changed_by=request.changed_by,
            )
            self.db.add(schema_record)

        await self.db.flush()
        logger.info(f"Updated table: {db_name}.{table_name} - {'; '.join(changes)}")

        return await self.get_table(db_name, table_name)

    async def drop_table(self, db_name: str, table_name: str) -> bool:
        """Drop a table."""
        result = await self.db.execute(
            select(CatalogTable)
            .join(CatalogDatabase)
            .where(CatalogDatabase.db_name == db_name)
            .where(CatalogTable.table_name == table_name)
        )
        table_record = result.scalar_one_or_none()
        if not table_record:
            return False

        await self.db.delete(table_record)
        await self.db.flush()
        logger.info(f"Dropped table: {db_name}.{table_name}")
        return True

    # ============================================
    # Snapshot Operations
    # ============================================

    async def get_table_snapshots(
        self, db_name: str, table_name: str
    ) -> Optional[SnapshotListResponse]:
        """Get snapshots for a table."""
        result = await self.db.execute(
            select(CatalogTable)
            .join(CatalogDatabase)
            .where(CatalogDatabase.db_name == db_name)
            .where(CatalogTable.table_name == table_name)
        )
        table_record = result.scalar_one_or_none()
        if not table_record:
            return None

        result = await self.db.execute(
            select(TableSnapshot)
            .where(TableSnapshot.table_id == table_record.table_id)
            .order_by(TableSnapshot.created_at.desc())
        )
        snapshots = result.scalars().all()

        return SnapshotListResponse(
            total=len(snapshots),
            table_name=table_name,
            snapshots=[
                SnapshotResponse(
                    snapshot_id=s.snapshot_id,
                    table_id=str(s.table_id),
                    parent_id=s.parent_id,
                    operation=s.operation,
                    manifest_list=s.manifest_list,
                    summary=s.summary,
                    created_at=s.created_at,
                )
                for s in snapshots
            ],
        )

