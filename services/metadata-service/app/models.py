from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# ============================================
# Database Models
# ============================================

class DatabaseCreateRequest(BaseModel):
    db_name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    owner: Optional[str] = None
    description: Optional[str] = None
    properties: dict = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "db_name": "sales_db",
                "owner": "data_engineering",
                "description": "Sales data warehouse",
                "properties": {"retention_days": 365},
            },
        }
    )

class DatabaseResponse(BaseModel):
    db_id: str
    db_name: str
    location: Optional[str] = None
    owner: Optional[str] = None
    description: Optional[str] = None
    properties: dict = Field(default_factory=dict)
    table_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatabaseListResponse(BaseModel):
    total: int
    databases: list[DatabaseResponse]


# ============================================
# Table Models
# ============================================

class ColumnSchema(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., description="Data type: string, int, long, double, float, boolean, timestamp, date, decimal, binary")
    nullable: bool = True
    description: Optional[str] = None


class TableCreateRequest(BaseModel):
    table_name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    table_type: str = Field(default="ICEBERG", description="ICEBERG, DELTA, HIVE, PARQUET")
    schema_fields: list[ColumnSchema] = Field(..., min_length=1)
    partition_spec: list[dict] = Field(default_factory=list)
    sort_order: list[dict] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)
    description: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "table_name": "transactions",
                "table_type": "ICEBERG",
                "schema_fields": [
                    {"name": "id", "type": "long", "nullable": False, "description": "Transaction ID"},
                    {"name": "amount", "type": "decimal", "nullable": False},
                    {"name": "currency", "type": "string", "nullable": True},
                    {"name": "transaction_date", "type": "timestamp", "nullable": False},
                    {"name": "customer_id", "type": "long", "nullable": False},
                ],
                "partition_spec": [{"field": "transaction_date", "transform": "day"}],
                "sort_order": [{"field": "transaction_date", "direction": "desc"}],
                "description": "Sales transactions table",
            },
        }
    )

class TableUpdateRequest(BaseModel):
    """For schema evolution and property updates."""
    add_columns: list[ColumnSchema] = Field(default_factory=list)
    drop_columns: list[str] = Field(default_factory=list)
    rename_columns: dict[str, str] = Field(default_factory=dict, description="old_name -> new_name")
    properties: Optional[dict] = None
    description: Optional[str] = None
    changed_by: Optional[str] = None


class TableResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_id: str
    db_name: str
    table_name: str
    table_type: str
    location: Optional[str] = None
    schema_payload: dict = Field(
        alias="schema_json",
        serialization_alias="schema_json",
    )
    partition_spec: list = Field(default_factory=list)
    sort_order: list = Field(default_factory=list)
    current_snapshot_id: Optional[int] = None
    properties: dict = Field(default_factory=dict)
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TableListResponse(BaseModel):
    total: int
    db_name: str
    tables: list[TableResponse]


# ============================================
# Snapshot Models
# ============================================

class SnapshotResponse(BaseModel):
    snapshot_id: int
    table_id: str
    parent_id: Optional[int] = None
    operation: Optional[str] = None
    manifest_list: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class SnapshotListResponse(BaseModel):
    total: int
    table_name: str
    snapshots: list[SnapshotResponse]

