from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import AssistantMessage, AssistantThread, Document
from app.schemas import AssistantChatIn, AssistantChatOut, AssistantMessageOut, AssistantThreadOut
from app.services.chat import (
    ASSISTANT_SYSTEM_PROMPT,
    HISTORY_MESSAGE_LIMIT,
    ChatAuthError,
    build_paper_context,
    chat_completion,
    chat_completion_stream,
    format_context_message,
)
from app.services.crypto_settings import decrypt_secret
from app.services.translate import get_default_provider

router = APIRouter(prefix="/api/documents/{document_id}/assistant", tags=["assistant"])


def _doc(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    return document


def _get_or_create_thread(db: Session, document_id: str) -> AssistantThread:
    thread = (
        db.query(AssistantThread).filter(AssistantThread.document_id == document_id).first()
    )
    if thread:
        return thread
    thread = AssistantThread(id=str(uuid.uuid4()), document_id=document_id)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def _message_out(msg: AssistantMessage) -> AssistantMessageOut:
    return AssistantMessageOut.model_validate(msg)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_llm_messages(
    db: Session,
    document: Document,
    thread_id: str,
    *,
    content: str,
    context_mode: str,
    page_index: int,
    block_id: str | None,
) -> tuple[list[dict[str, str]], Any]:
    ctx = build_paper_context(
        db,
        document,
        context_mode=context_mode,
        page_index=page_index,
        block_id=block_id,
    )
    history = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.thread_id == thread_id)
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    if len(history) > HISTORY_MESSAGE_LIMIT:
        history = history[-HISTORY_MESSAGE_LIMIT:]

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
        {"role": "user", "content": format_context_message(document, ctx)},
        {
            "role": "assistant",
            "content": "Understood. I will answer using the paper context you provided.",
        },
    ]
    for msg in history:
        if msg.role in ("user", "assistant") and msg.content:
            llm_messages.append({"role": msg.role, "content": msg.content})
    llm_messages.append({"role": "user", "content": content})
    return llm_messages, ctx


@router.get("/messages", response_model=AssistantThreadOut)
def list_messages(document_id: str, db: Session = Depends(get_db)) -> AssistantThreadOut:
    _doc(db, document_id)
    thread = _get_or_create_thread(db, document_id)
    messages = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.thread_id == thread.id)
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    return AssistantThreadOut(
        thread_id=thread.id,
        messages=[_message_out(m) for m in messages],
    )


@router.delete("/messages")
def clear_messages(document_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    _doc(db, document_id)
    thread = _get_or_create_thread(db, document_id)
    db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread.id).delete()
    db.commit()
    return {"status": "cleared"}


@router.post("/chat", response_model=AssistantChatOut)
async def chat(
    document_id: str, body: AssistantChatIn, db: Session = Depends(get_db)
) -> AssistantChatOut:
    document = _doc(db, document_id)
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "Message content is required")

    provider = get_default_provider(db)
    if not provider:
        raise HTTPException(
            503,
            "No translation provider configured. Add one in Settings first.",
        )

    thread = _get_or_create_thread(db, document_id)
    llm_messages, ctx = _build_llm_messages(
        db,
        document,
        thread.id,
        content=content,
        context_mode=body.context_mode,
        page_index=body.page_index,
        block_id=body.block_id,
    )

    api_key = decrypt_secret(provider.api_key_enc) if provider.api_key_enc else ""
    try:
        reply = await chat_completion(
            provider.base_url,
            api_key,
            provider.model,
            llm_messages,
            is_full_url=bool(provider.is_full_url),
            temperature=0.4,
        )
    except ChatAuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Assistant request failed: {exc}") from exc

    user_msg = AssistantMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        role="user",
        content=content,
        context_mode=ctx.mode,
        page_index=ctx.page_index if ctx.page_index is not None else body.page_index,
        block_id=ctx.block_id,
    )
    assistant_msg = AssistantMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        role="assistant",
        content=reply,
        context_mode=None,
        page_index=None,
        block_id=None,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return AssistantChatOut(
        thread_id=thread.id,
        user_message=_message_out(user_msg),
        assistant_message=_message_out(assistant_msg),
    )


@router.post("/chat/stream")
async def chat_stream(
    document_id: str, body: AssistantChatIn, db: Session = Depends(get_db)
) -> StreamingResponse:
    document = _doc(db, document_id)
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "Message content is required")

    provider = get_default_provider(db)
    if not provider:
        raise HTTPException(
            503,
            "No translation provider configured. Add one in Settings first.",
        )

    thread = _get_or_create_thread(db, document_id)
    llm_messages, ctx = _build_llm_messages(
        db,
        document,
        thread.id,
        content=content,
        context_mode=body.context_mode,
        page_index=body.page_index,
        block_id=body.block_id,
    )

    user_msg = AssistantMessage(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        role="user",
        content=content,
        context_mode=ctx.mode,
        page_index=ctx.page_index if ctx.page_index is not None else body.page_index,
        block_id=ctx.block_id,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)
    user_out = _message_out(user_msg).model_dump(mode="json")

    provider_snap = {
        "base_url": provider.base_url,
        "model": provider.model,
        "is_full_url": bool(provider.is_full_url),
        "api_key": decrypt_secret(provider.api_key_enc) if provider.api_key_enc else "",
    }
    thread_id = thread.id

    async def event_gen() -> AsyncIterator[str]:
        yield _sse({"type": "user", "thread_id": thread_id, "message": user_out})
        parts: list[str] = []
        try:
            async for piece in chat_completion_stream(
                provider_snap["base_url"],
                provider_snap["api_key"],
                provider_snap["model"],
                llm_messages,
                is_full_url=provider_snap["is_full_url"],
                temperature=0.4,
            ):
                parts.append(piece)
                yield _sse({"type": "delta", "text": piece})
        except ChatAuthError as exc:
            yield _sse({"type": "error", "detail": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "detail": f"Assistant request failed: {exc}"})
            return

        reply = "".join(parts).strip()
        assistant_out: dict[str, Any]
        db2 = SessionLocal()
        try:
            assistant_msg = AssistantMessage(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                role="assistant",
                content=reply or "(empty reply)",
                context_mode=None,
                page_index=None,
                block_id=None,
            )
            db2.add(assistant_msg)
            db2.commit()
            db2.refresh(assistant_msg)
            assistant_out = _message_out(assistant_msg).model_dump(mode="json")
        finally:
            db2.close()

        yield _sse({"type": "done", "thread_id": thread_id, "message": assistant_out})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
