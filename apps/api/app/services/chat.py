from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session, joinedload

from app.models import Block, Document
from app.services.openai_url import openai_chat_completions_url

PAGE_CHAR_LIMIT = 12_000
FULL_CHAR_LIMIT = 40_000
HISTORY_MESSAGE_LIMIT = 40

ASSISTANT_SYSTEM_PROMPT = (
    "You are a paper-reading assistant. Help the user understand the scholarly paper. "
    "Answer in the user's language (default Simplified Chinese if unclear). "
    "Be precise; quote or paraphrase the paper when helpful. "
    "Do not invent citations or results not in the provided context."
)

TEXT_BLOCK_TYPES = ("text", "caption", "heading", "title", "meta")


class ChatAuthError(Exception):
    """Provider rejected credentials / access."""


async def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    is_full_url: bool = False,
    temperature: float = 0.4,
    timeout: float = 120.0,
) -> str:
    url = openai_chat_completions_url(base_url, is_full_url=is_full_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (401, 403):
            raise ChatAuthError(
                f"Provider returned {resp.status_code}. Check Base URL, API key, and model in Settings."
            )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def chat_completion_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    is_full_url: bool = False,
    temperature: float = 0.4,
    timeout: float = 180.0,
) -> AsyncIterator[str]:
    """Yield text deltas from an OpenAI-compatible streaming chat completion."""
    url = openai_chat_completions_url(base_url, is_full_url=is_full_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code in (401, 403):
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise ChatAuthError(
                    f"Provider returned {resp.status_code}. Check Base URL, API key, and model in Settings."
                    + (f" {body[:200]}" if body else "")
                )
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Provider returned {resp.status_code}. Check Base URL, API key, and model in Settings."
                    + (f" {body[:300]}" if body else "")
                )
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    if data == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece


@dataclass
class BuiltContext:
    mode: str  # block | page | full
    label: str
    text: str
    page_index: int | None
    block_id: str | None


def _format_block_line(block: Block) -> str:
    line = (block.text or "").strip()
    if not line:
        return ""
    if block.translation and block.translation.text:
        zh = block.translation.text.strip()
        if zh:
            return f"{line}\n[译] {zh}"
    return line


def _join_blocks(blocks: list[Block], char_limit: int) -> tuple[str, bool]:
    parts: list[str] = []
    total = 0
    truncated = False
    for block in blocks:
        if block.block_type not in TEXT_BLOCK_TYPES:
            continue
        piece = _format_block_line(block)
        if not piece:
            continue
        if total + len(piece) + 2 > char_limit:
            truncated = True
            break
        parts.append(piece)
        total += len(piece) + 2
    text = "\n\n".join(parts)
    if truncated:
        text += "\n\n[… context truncated …]"
    return text, truncated


def build_paper_context(
    db: Session,
    document: Document,
    *,
    context_mode: str,
    page_index: int,
    block_id: str | None,
) -> BuiltContext:
    """Resolve auto/full/page/block into block|page|full and return assembled text."""
    mode_req = (context_mode or "auto").strip().lower()
    if mode_req not in ("auto", "full", "page", "block"):
        mode_req = "auto"

    if mode_req == "full":
        blocks = (
            db.query(Block)
            .options(joinedload(Block.translation))
            .filter(Block.document_id == document.id)
            .order_by(Block.page_index, Block.block_index)
            .all()
        )
        text, _ = _join_blocks(blocks, FULL_CHAR_LIMIT)
        return BuiltContext(
            mode="full",
            label="full document",
            text=text or "(No extractable text in this document.)",
            page_index=None,
            block_id=None,
        )

    want_block = mode_req in ("auto", "block") and bool(block_id)
    if want_block:
        block = (
            db.query(Block)
            .options(joinedload(Block.translation))
            .filter(Block.id == block_id, Block.document_id == document.id)
            .first()
        )
        if block:
            piece = _format_block_line(block) or "(Empty block.)"
            return BuiltContext(
                mode="block",
                label=f"selected passage · page {block.page_index + 1}",
                text=piece,
                page_index=block.page_index,
                block_id=block.id,
            )
        if mode_req == "block":
            # Missing block — fall through to page scope.
            pass

    page = max(0, int(page_index))
    blocks = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(Block.document_id == document.id, Block.page_index == page)
        .order_by(Block.block_index)
        .all()
    )
    text, _ = _join_blocks(blocks, PAGE_CHAR_LIMIT)
    return BuiltContext(
        mode="page",
        label=f"current page · page {page + 1}",
        text=text or "(No extractable text on this page.)",
        page_index=page,
        block_id=None,
    )


def format_context_message(document: Document, ctx: BuiltContext) -> str:
    title = document.title or document.filename or "Untitled"
    return (
        f"Document: {title}\n"
        f"Context scope: {ctx.label}\n"
        f"---\n"
        f"{ctx.text}"
    )
