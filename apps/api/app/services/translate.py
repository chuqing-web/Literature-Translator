from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session, joinedload

from app.models import AppSetting, Block, ProviderProfile, TranslateJob, Translation
from app.services.chat import ChatAuthError, chat_completion
from app.services.crypto_settings import decrypt_secret

SYSTEM_PROMPT = (
    "You are an academic translator. Translate the user's English scholarly text into "
    "natural Simplified Chinese. Preserve meaning, technical terms, and paragraph breaks. "
    "Keep URLs, emails, DOIs, and citation keys unchanged. "
    "If the input is only links, affiliations, or author names, translate labels only and "
    "keep proper nouns/URLs as-is. Do not add explanations. Output translation only."
)


class TranslateAuthError(Exception):
    """Provider rejected credentials / access."""

def get_default_provider(db: Session) -> ProviderProfile | None:
    setting = db.get(AppSetting, "ui")
    active_id = None
    if setting:
        try:
            active_id = json.loads(setting.value).get("active_provider_id")
        except json.JSONDecodeError:
            active_id = None
    if active_id:
        profile = db.get(ProviderProfile, active_id)
        if profile:
            return profile
    return (
        db.query(ProviderProfile)
        .filter(ProviderProfile.is_default.is_(True))
        .first()
        or db.query(ProviderProfile).first()
    )


async def translate_text(
    base_url: str,
    api_key: str,
    model: str,
    text: str,
    *,
    is_full_url: bool = False,
) -> str:
    try:
        return await chat_completion(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            is_full_url=is_full_url,
            temperature=0.2,
        )
    except ChatAuthError as exc:
        raise TranslateAuthError(str(exc)) from exc

async def run_translate_job(db: Session, job_id: str) -> None:
    job = db.get(TranslateJob, job_id)
    if not job:
        return
    provider = get_default_provider(db)
    if not provider:
        job.status = "error"
        job.error = "No provider configured. Add one in Settings."
        db.commit()
        return

    api_key = decrypt_secret(provider.api_key_enc)
    if not api_key and "localhost" not in provider.base_url and "127.0.0.1" not in provider.base_url:
        pass

    blocks = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(
            Block.document_id == job.document_id,
            Block.block_type.in_(("text", "caption", "heading", "title", "meta")),
        )
        .order_by(Block.page_index, Block.block_index)
        .all()
    )
    todo: list[Block] = []
    for b in blocks:
        if b.translation and b.translation.text and b.translation.edited:
            continue
        if b.translation and b.translation.text and b.translation.status == "done":
            continue
        todo.append(b)

    job.total = len(todo)
    job.done = 0
    job.status = "running"
    job.error = ""
    db.commit()

    consecutive_failures = 0
    for block in todo:
        try:
            translated = await translate_text(
                provider.base_url,
                api_key or "ollama",
                provider.model,
                block.text,
                is_full_url=bool(provider.is_full_url),
            )
            consecutive_failures = 0
            if block.translation:
                if not block.translation.edited:
                    block.translation.text = translated
                    block.translation.model = provider.model
                    block.translation.provider_profile = provider.name
                    block.translation.status = "done"
            else:
                db.add(
                    Translation(
                        id=str(uuid.uuid4()),
                        block_id=block.id,
                        provider_profile=provider.name,
                        model=provider.model,
                        text=translated,
                        edited=False,
                        status="done",
                    )
                )
            job.done += 1
            db.commit()
        except TranslateAuthError as exc:
            if block.translation:
                block.translation.status = "error"
                block.translation.text = ""
            else:
                db.add(
                    Translation(
                        id=str(uuid.uuid4()),
                        block_id=block.id,
                        provider_profile=provider.name,
                        model=provider.model,
                        text="",
                        edited=False,
                        status="error",
                    )
                )
            job.status = "error"
            job.error = str(exc)
            job.done += 1
            db.commit()
            return
        except Exception as exc:  # noqa: BLE001
            consecutive_failures += 1
            if block.translation:
                block.translation.status = "error"
                block.translation.text = ""
            else:
                db.add(
                    Translation(
                        id=str(uuid.uuid4()),
                        block_id=block.id,
                        provider_profile=provider.name,
                        model=provider.model,
                        text="",
                        edited=False,
                        status="error",
                    )
                )
            job.error = str(exc)
            job.done += 1
            db.commit()
            if consecutive_failures >= 5:
                job.status = "error"
                job.error = f"Stopped after repeated failures: {exc}"
                db.commit()
                return

    job.status = "done" if not job.error else "done_with_errors"
    db.commit()
