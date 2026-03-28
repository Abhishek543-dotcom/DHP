# Postman Assets

## Files

- `lakehouse-platform.postman_collection.json`
- `lakehouse-platform.local.postman_environment.json`

## Import

1. Open Postman.
2. Import both files from this folder.
3. Select the **Lakehouse Platform Local** environment.

## Run Order (for smoke test)

Run folders in this sequence:

1. Job Service
2. Metadata Service
3. Storage Service
4. Log Service

`Log Streaming (Manual)` is an SSE endpoint and should be run manually.
