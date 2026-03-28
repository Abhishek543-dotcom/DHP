import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, BigInteger, DateTime, func, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CatalogDatabase(Base):
    """SQLAlchemy model for catalog databases (namespaces)."""

    __tablename__ = "catalog_databases"

    db_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    db_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tables = relationship("CatalogTable", back_populates="database", cascade="all, delete-orphan")


class CatalogTable(Base):
    """SQLAlchemy model for catalog tables."""

    __tablename__ = "catalog_tables"
    __table_args__ = (UniqueConstraint("db_id", "table_name"),)

    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    db_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_databases.db_id", ondelete="CASCADE"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_type: Mapped[str] = mapped_column(String(50), default="ICEBERG")
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    partition_spec: Mapped[list] = mapped_column(JSONB, default=list)
    sort_order: Mapped[list] = mapped_column(JSONB, default=list)
    current_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    database = relationship("CatalogDatabase", back_populates="tables")
    snapshots = relationship("TableSnapshot", back_populates="table", cascade="all, delete-orphan")


class TableSnapshot(Base):
    """SQLAlchemy model for table snapshots (Iceberg)."""

    __tablename__ = "table_snapshots"

    snapshot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_tables.table_id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    manifest_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    table = relationship("CatalogTable", back_populates="snapshots")


class SchemaHistory(Base):
    """SQLAlchemy model for schema evolution history."""

    __tablename__ = "schema_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_tables.table_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

