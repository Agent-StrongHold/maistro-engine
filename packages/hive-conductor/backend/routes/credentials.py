"""Per-user integration credentials — encrypted at rest, never returned in API responses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from maistro.credentials import get_provider
from maistro.credentials.store import CredentialStoreUnavailable
from routes.audit import log_audit
from services import user_credentials as cred_svc

router = APIRouter(tags=["credentials"])


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(uid)


class SetCredentialBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    secret: str = Field(min_length=1, max_length=4096)


@router.get("/providers")
def list_providers() -> dict[str, Any]:
    return {"providers": cred_svc.list_provider_catalog()}


@router.get("")
def list_my_credentials(request: Request) -> dict[str, Any]:
    uid = _user_id(request)
    try:
        store = cred_svc.require_store()
    except CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    configured = store.list_providers_for_user(uid)
    catalog = cred_svc.list_provider_catalog()
    items = []
    for entry in catalog:
        meta = configured.get(entry["id"], {})
        items.append(
            {
                **entry,
                "configured": entry["id"] in configured,
                "updated_at": meta.get("updated_at"),
            }
        )
    return {"credentials": items}


@router.put("/{provider_id}")
def save_credential(
    provider_id: str,
    body: SetCredentialBody,
    request: Request,
) -> dict[str, Any]:
    # SECURITY-REVIEW: user-controlled secret written to Fernet-encrypted store scoped by session user id.
    if get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="Unknown credential provider")
    uid = _user_id(request)
    try:
        store = cred_svc.require_store()
        store.set_secret(uid, provider_id, body.secret)
    except CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_audit("credential_save", uid, target=provider_id)
    return {"ok": True, "provider": provider_id, "configured": True}


@router.delete("/{provider_id}", status_code=204)
def delete_credential(provider_id: str, request: Request) -> None:
    if get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="Unknown credential provider")
    uid = _user_id(request)
    try:
        store = cred_svc.require_store()
        if not store.delete_secret(uid, provider_id):
            raise HTTPException(status_code=404, detail="Credential not configured")
    except CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    log_audit("credential_delete", uid, target=provider_id)
