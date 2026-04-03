from typing import List

from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field

from app.security import require_api_key

router = APIRouter(prefix="/api/v1/clusters", tags=["Clusters"])


class NamespaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=63)


class NamespaceResponse(BaseModel):
    name: str
    status: str


class NamespaceListResponse(BaseModel):
    namespaces: List[str]


def _load_k8s_config() -> None:
    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Kubernetes config not available for cluster operations",
            ) from exc


@router.post("/namespaces", response_model=NamespaceResponse, dependencies=[Depends(require_api_key)])
def create_namespace(request: NamespaceCreateRequest):
    _load_k8s_config()
    core_api = client.CoreV1Api()

    try:
        core_api.read_namespace(name=request.name)
        return NamespaceResponse(name=request.name, status="exists")
    except ApiException as exc:
        if exc.status != 404:
            raise HTTPException(status_code=500, detail=f"Failed to read namespace: {exc}") from exc

    try:
        ns = client.V1Namespace(metadata=client.V1ObjectMeta(name=request.name))
        core_api.create_namespace(ns)
        return NamespaceResponse(name=request.name, status="created")
    except ApiException as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create namespace: {exc}") from exc


@router.get("/namespaces", response_model=NamespaceListResponse, dependencies=[Depends(require_api_key)])
def list_namespaces():
    _load_k8s_config()
    core_api = client.CoreV1Api()
    try:
        namespaces = core_api.list_namespace().items
        return NamespaceListResponse(
            namespaces=sorted([n.metadata.name for n in namespaces if n.metadata and n.metadata.name])
        )
    except ApiException as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list namespaces: {exc}") from exc
