import json
from typing import Any

import requests
import streamlit as st

st.set_page_config(page_title="DHP Control Plane", page_icon="⚙️", layout="wide")

st.title("⚙️ DataHarbour Control Plane")
st.caption("Unified UI for pipeline operations, SQL jobs, metadata, storage, and cluster namespaces.")

with st.sidebar:
    st.header("Connection")
    api_key = st.text_input("X-API-Key", value="dev-api-key-change-me", type="password")
    job_base = st.text_input("Job Service URL", value="http://job-service:8000")
    metadata_base = st.text_input("Metadata Service URL", value="http://metadata-service:8000")
    storage_base = st.text_input("Storage Service URL", value="http://storage-service:8000")
    timeout_sec = st.slider("HTTP timeout (sec)", min_value=5, max_value=90, value=30)


def _headers() -> dict[str, str]:
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def _call(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[bool, Any]:
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_headers(),
            json=payload,
            timeout=timeout_sec,
        )
        try:
            data = response.json()
        except ValueError:
            data = response.text
        if response.ok:
            return True, data
        return False, {"status": response.status_code, "error": data}
    except requests.RequestException as exc:
        return False, {"error": str(exc)}


def show_result(ok: bool, data: Any):
    if ok:
        st.success("Success")
    else:
        st.error("Request failed")
    st.json(data)


tab_jobs, tab_sql, tab_meta, tab_storage, tab_cluster = st.tabs(
    ["Pipelines / Jobs", "SQL Runner", "Metadata", "Storage", "Cluster"]
)

with tab_jobs:
    st.subheader("Pipeline Job Lifecycle")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Submit pipeline job")
        job_name = st.text_input("Job name", value="pipeline-orders-daily")
        job_type = st.selectbox("Job type", ["spark_etl", "spark_sql", "spark_ml", "spark_streaming"], index=0)
        entrypoint = st.text_input("Entrypoint", value="s3://lakehouse-scripts/etl/sales_transform.py")
        submitted_by = st.text_input("Submitted by", value="streamlit-ui")
        args_json = st.text_area("Arguments (JSON array)", value="[]")
        spark_conf_json = st.text_area("Spark config (JSON object)", value="{}")

        if st.button("Submit Job", key="submit_job"):
            try:
                payload = {
                    "job_name": job_name,
                    "job_type": job_type,
                    "entrypoint": entrypoint,
                    "submitted_by": submitted_by,
                    "arguments": json.loads(args_json),
                    "spark_config": json.loads(spark_conf_json),
                }
                show_result(*_call("POST", f"{job_base}/api/v1/jobs/", payload))
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON input: {exc}")

    with col2:
        st.markdown("#### Monitor / control jobs")
        if st.button("List Jobs", key="list_jobs"):
            show_result(*_call("GET", f"{job_base}/api/v1/jobs/"))

        job_id_lookup = st.text_input("Job ID")
        c1, c2, c3 = st.columns(3)
        if c1.button("Get Job", key="get_job"):
            show_result(*_call("GET", f"{job_base}/api/v1/jobs/{job_id_lookup}"))
        if c2.button("Cancel Job", key="cancel_job"):
            show_result(*_call("DELETE", f"{job_base}/api/v1/jobs/{job_id_lookup}"))
        if c3.button("Get Logs", key="logs_job"):
            show_result(*_call("GET", f"{job_base}/api/v1/jobs/{job_id_lookup}/logs"))

with tab_sql:
    st.subheader("SQL Runner (submits Spark SQL job)")
    sql_text = st.text_area(
        "SQL query",
        value="SELECT * FROM demo.orders LIMIT 10;",
        height=180,
    )
    sql_entrypoint = st.text_input("SQL entrypoint", value="inline-sql")
    sql_submitter = st.text_input("Submitted by", value="streamlit-sql")

    if st.button("Run SQL", key="run_sql"):
        payload = {
            "job_name": f"sql-query-{abs(hash(sql_text)) % 100000}",
            "job_type": "spark_sql",
            "entrypoint": sql_entrypoint,
            "submitted_by": sql_submitter,
            "arguments": [sql_text],
            "spark_config": {"spark.sql.query": sql_text},
        }
        show_result(*_call("POST", f"{job_base}/api/v1/jobs/", payload))

with tab_meta:
    st.subheader("Catalog / Metadata")
    c1, c2 = st.columns(2)

    with c1:
        db_name = st.text_input("Database name", value="demo")
        if st.button("Create Database", key="create_db"):
            show_result(
                *_call(
                    "POST",
                    f"{metadata_base}/api/v1/databases/",
                    {"db_name": db_name, "description": "created-via-streamlit"},
                )
            )
        if st.button("List Databases", key="list_db"):
            show_result(*_call("GET", f"{metadata_base}/api/v1/databases/"))

    with c2:
        table_name = st.text_input("Table name", value="orders")
        schema_json = st.text_area(
            "Schema fields (JSON array)",
            value='[{"name":"id","type":"int","nullable":false},{"name":"amount","type":"double","nullable":true}]',
            height=120,
        )
        if st.button("Create Table", key="create_table"):
            try:
                payload = {"table_name": table_name, "schema_fields": json.loads(schema_json)}
                show_result(
                    *_call(
                        "POST",
                        f"{metadata_base}/api/v1/databases/{db_name}/tables/",
                        payload,
                    )
                )
            except json.JSONDecodeError as exc:
                st.error(f"Invalid schema JSON: {exc}")

with tab_storage:
    st.subheader("Object Storage")
    b1, b2 = st.columns(2)

    with b1:
        bucket_name = st.text_input("Bucket name", value="demo-bucket")
        if st.button("Create Bucket", key="create_bucket"):
            show_result(*_call("POST", f"{storage_base}/api/v1/storage/buckets", {"name": bucket_name}))
        if st.button("List Buckets", key="list_buckets"):
            show_result(*_call("GET", f"{storage_base}/api/v1/storage/buckets"))

    with b2:
        object_bucket = st.text_input("Bucket for object listing", value="demo-bucket")
        if st.button("List Objects", key="list_objects"):
            show_result(*_call("GET", f"{storage_base}/api/v1/storage/buckets/{object_bucket}/objects"))

with tab_cluster:
    st.subheader("Cluster Environment")
    st.caption("Namespace-based cluster workspace management via Job Service API")
    namespace_name = st.text_input("Namespace", value="dhp-dev")
    a, b = st.columns(2)
    if a.button("Create Namespace", key="create_ns"):
        show_result(*_call("POST", f"{job_base}/api/v1/clusters/namespaces", {"name": namespace_name}))
    if b.button("List Namespaces", key="list_ns"):
        show_result(*_call("GET", f"{job_base}/api/v1/clusters/namespaces"))
