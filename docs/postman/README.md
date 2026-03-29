# Postman Guide

This folder contains Postman assets for running the full DataHarbour Project (DHP) API suite against local development infrastructure.

## Files

- `lakehouse-platform.postman_collection.json`
- `lakehouse-platform.local.postman_environment.json`

## What the Collection Covers

Collection name: `DataHarbour Project (DHP) API (Local)`

Folders:

1. `Job Service`
2. `Metadata Service`
3. `Storage Service`
4. `Log Service`
5. `Log Streaming (Manual)`

## Import Steps

1. Open Postman.
2. Import both files from this folder.
3. Select environment `DataHarbour Project (DHP) Local`.

## Environment Variables

Important variables in the provided environment:

- `job_service_url` = `http://localhost:8001`
- `metadata_service_url` = `http://localhost:8002`
- `log_service_url` = `http://localhost:8003`
- `storage_service_url` = `http://localhost:8004`
- `api_key` = `dev-api-key-change-me`
- `internal_token` = `dev-internal-token-change-me`
- `job_id`, `run_id` for dynamic request chaining

Also includes defaults for `db_name`, `table_name`, `bucket_name`, `object_key`, and `entrypoint`.

## Suggested Execution Order

Run folders in this sequence for best results:

1. `Metadata Service` (create namespace/table first)
2. `Storage Service` (ensure buckets/object paths)
3. `Job Service` (submit and monitor jobs)
4. `Log Service` (retrieve logs for created jobs)

`Log Streaming (Manual)` should be called manually due to Server-Sent Events behavior.

## Runner Usage

Use Collection Runner with:

- Environment: `DataHarbour Project (DHP) Local`
- Save responses enabled
- Stop run on first error disabled (for broad validation)

After run completion, review:

- Non-2xx responses
- Missing `job_id` propagation between requests
- Endpoint auth failures (`X-API-Key` mismatch)

## Common Issues

- `401 Unauthorized`: environment `api_key` does not match running stack `.env`.
- `5xx on job submit`: Kafka or orchestrator not healthy.
- Empty logs: Loki not ready yet or job has not produced logs.
- SSE stream appears stalled: expected if target job is already completed.
