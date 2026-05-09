# DHP Database Migrations

Single-source-of-truth schema for DHP, managed by Alembic. The
`job-service` and `metadata-service` share one PostgreSQL database, so
a single migrations directory is simpler than two parallel chains.

## Apply migrations

Locally:

```bash
cd db
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://lakehouse:dev-db-password-change-me@localhost:5432/lakehouse \
    alembic upgrade head
```

In CI/CD: the ECS deployment registers an `init-migrations` task that
runs `alembic upgrade head` against RDS before the API services start.

## Stamping an existing database

If you already created the schema by running `scripts/init-db.sql`
(local docker-compose), tell Alembic the schema is at the baseline:

```bash
DATABASE_URL=... alembic stamp 0001
```

## Creating a new migration

```bash
DATABASE_URL=... alembic revision -m "add table xyz"
# Edit the generated file in db/migrations/versions/
DATABASE_URL=... alembic upgrade head
```

We use raw SQL (`op.execute(...)`) rather than autogenerate because the
SQLAlchemy models live in two separate services; keeping migrations
declarative-SQL avoids cross-service model imports.
