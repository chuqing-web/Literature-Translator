from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AssistantMessage, AssistantThread, Document
from app.schemas import AssistantChatIn, AssistantChatOut, AssistantMessageOut, AssistantThreadOut
from app.services.chat import (
    ASSISTANT_SYSTEM_PROMPT,
    HISTORY_MESSAGE_LIMIT,
    ChatAuthError,
    build_paper_context,
    chat_completion,
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
    ctx = build_paper_context(
        db,
        document,
        context_mode=body.context_mode,
        page_index=body.page_index,
        block_id=body.block_id,
    )

    history = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.thread_id == thread.id)
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
