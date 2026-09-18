from __future__ import annotations

import json
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import AppSetting, Block, Document, ProviderProfile
from app.schemas import (
    ProviderIn,
    ProviderOut,
    ProviderPresetOut,
    ProviderTestOut,
    SettingsOut,
    SettingsUpdate,
    UrlPreviewIn,
    UrlPreviewOut,
)
from app.services.crypto_settings import decrypt_secret, encrypt_secret
from app.services.openai_url import (
    PROVIDER_PRESETS,
    normalize_base_url,
    openai_chat_completions_url,
)

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULT_UI = {
    "view_mode": "embedded",
    "font_family": "Source Han Serif SC, Noto Serif SC, serif",
    "font_size": 14,
    "line_height": 1.4,
    "active_provider_id": None,
    "locale": "zh",
}


def _load_ui(db: Session) -> dict:
    row = db.get(AppSetting, "ui")
    if not row:
        return dict(DEFAULT_UI)
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return dict(DEFAULT_UI)
    merged = dict(DEFAULT_UI)
    merged.update(data)
    return merged


def _save_ui(db: Session, data: dict) -> None:
    row = db.get(AppSetting, "ui")
    payload = json.dumps(data, ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(AppSetting(key="ui", value=payload))
    db.commit()


def _provider_out(p: ProviderProfile) -> ProviderOut:
    is_full = bool(getattr(p, "is_full_url", False))
    try:
        resolved = openai_chat_completions_url(p.base_url, is_full_url=is_full)
    except ValueError:
        resolved = ""
    return ProviderOut(
        id=p.id,
        name=p.name,
        base_url=p.base_url,
        model=p.model,
        is_default=p.is_default,
        has_api_key=bool(p.api_key_enc),
        is_full_url=is_full,
        resolved_url=resolved,
    )


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)) -> SettingsOut:
    return SettingsOut(**_load_ui(db))


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsOut:
    data = _load_ui(db)
    for key, value in body.model_dump(exclude_none=True).items():
        data[key] = value
    _save_ui(db, data)
    return SettingsOut(**data)


@router.get("/provider-presets", response_model=list[ProviderPresetOut])
def list_provider_presets() -> list[ProviderPresetOut]:
    return [ProviderPresetOut(**p) for p in PROVIDER_PRESETS]


@router.post("/providers/preview-url", response_model=UrlPreviewOut)
def preview_provider_url(body: UrlPreviewIn) -> UrlPreviewOut:
    try:
        resolved = openai_chat_completions_url(body.base_url, is_full_url=body.is_full_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return UrlPreviewOut(
        resolved_url=resolved,
        mode="full" if body.is_full_url else "prefix",
    )


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderOut]:
    rows = db.query(ProviderProfile).order_by(ProviderProfile.name).all()
    return [_provider_out(p) for p in rows]


@router.post("/providers", response_model=ProviderOut)
def create_provider(body: ProviderIn, db: Session = Depends(get_db)) -> ProviderOut:
    if body.is_default:
        for p in db.query(ProviderProfile).all():
            p.is_default = False
    profile = ProviderProfile(
        id=str(uuid.uuid4()),
        name=body.name,
        base_url=normalize_base_url(body.base_url),
        api_key_enc=encrypt_secret(body.api_key) if body.api_key else "",
        model=body.model,
        is_default=body.is_default,
        is_full_url=body.is_full_url,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    ui = _load_ui(db)
    if body.is_default or not ui.get("active_provider_id"):
        ui["active_provider_id"] = profile.id
        _save_ui(db, ui)
    return _provider_out(profile)


@router.put("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: str, body: ProviderIn, db: Session = Depends(get_db)
) -> ProviderOut:
    profile = db.get(ProviderProfile, provider_id)
    if not profile:
        raise HTTPException(404, "Provider not found")
    if body.is_default:
        for p in db.query(ProviderProfile).all():
            p.is_default = False
    profile.name = body.name
    profile.base_url = normalize_base_url(body.base_url)
    profile.model = body.model
    profile.is_default = body.is_default
    profile.is_full_url = body.is_full_url
    if body.api_key:
        profile.api_key_enc = encrypt_secret(body.api_key)
    db.commit()
    db.refresh(profile)
    if body.is_default:
        ui = _load_ui(db)
        ui["active_provider_id"] = profile.id
        _save_ui(db, ui)
    return _provider_out(profile)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    profile = db.get(ProviderProfile, provider_id)
    if not profile:
        raise HTTPException(404, "Provider not found")
    db.delete(profile)
    db.commit()
    return {"status": "deleted"}


@router.post("/providers/{provider_id}/test", response_model=ProviderTestOut)
async def test_provider(provider_id: str, db: Session = Depends(get_db)) -> ProviderTestOut:
    profile = db.get(ProviderProfile, provider_id)
    if not profile:
        raise HTTPException(404, "Provider not found")

    api_key = decrypt_secret(profile.api_key_enc)
    try:
        url = openai_chat_completions_url(
            profile.base_url, is_full_url=bool(getattr(profile, "is_full_url", False))
        )
    except ValueError as exc:
        return ProviderTestOut(ok=False, message=str(exc), resolved_url="")
    headers = {
        "Authorization": f"Bearer {api_key or 'ollama'}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": profile.model,
        "temperature": 0,
        "max_tokens": 16,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: OK",
            }
        ],
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code in (401, 403):
            return ProviderTestOut(
                ok=False,
                message=f"Auth failed ({resp.status_code}). Check API key / account permission.",
                latency_ms=latency_ms,
                resolved_url=url,
            )
        if resp.status_code >= 400:
            detail = resp.text[:240]
            return ProviderTestOut(
                ok=False,
                message=f"HTTP {resp.status_code}: {detail}",
                latency_ms=latency_ms,
                resolved_url=url,
            )

        data = resp.json()
        sample = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return ProviderTestOut(
            ok=True,
            message=f"Connected · {profile.model}",
            latency_ms=latency_ms,
            sample=sample[:80] or None,
            resolved_url=url,
        )
    except httpx.TimeoutException:
        return ProviderTestOut(
            ok=False,
            message="Timed out after 30s. Check Base URL / network.",
            latency_ms=int((time.perf_counter() - started) * 1000),
            resolved_url=url,
        )
    except httpx.HTTPError as exc:
        return ProviderTestOut(
            ok=False,
            message=f"Network error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
            resolved_url=url,
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderTestOut(
            ok=False,
            message=f"Unexpected error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
            resolved_url=url,
        )


@router.get("/documents/{document_id}/export.docx")
def export_docx(document_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    from docx import Document as DocxDocument
    from io import BytesIO

    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    blocks = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(Block.document_id == document_id)
        .order_by(Block.page_index, Block.block_index)
        .all()
    )
    docx = DocxDocument()
    docx.add_heading(document.title or document.filename, level=1)
    current_page = -1
    for block in blocks:
        if block.page_index != current_page:
            current_page = block.page_index
            docx.add_heading(f"Page {current_page + 1}", level=2)
        if block.block_type == "formula_skip":
            continue
        docx.add_paragraph(block.text)
        if block.translation and block.translation.text:
            p = docx.add_paragraph(block.translation.text)
            p.runs[0].italic = True if p.runs else False

    buf = BytesIO()
    docx.save(buf)
    buf.seek(0)
    filename = f"{document.title or 'export'}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# silence unused import warning for decrypt in future debug endpoints
_ = decrypt_secret
