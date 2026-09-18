from __future__ import annotations

import json
import re
import uuid

from sqlalchemy.orm import Session, joinedload

from app.models import AppSetting, Block, ProviderProfile, TranslateJob, Translation
from app.services.chat import ChatAuthError, chat_completion
from app.services.crypto_settings import decrypt_secret
from app.services.math_text import (
    is_author_line_text,
    is_formula_like_text,
    sanitize_math_translation,
    soft_unwrap,
)
from app.services.pdf_parse import repair_wrapped_paragraph_blocks

SYSTEM_PROMPT = (
    "You are an academic translator. Translate the user's English scholarly text into "
    "natural Simplified Chinese. Preserve meaning, technical terms, and real paragraph "
    "breaks (blank lines). Do NOT keep soft line wraps from PDF layout — join wrapped "
    "words into normal flowing Chinese sentences. "
    "Keep URLs, emails, DOIs, and citation keys unchanged. "
    "IMPORTANT — length: keep Chinese concise and compact. Prefer shorter phrasing; "
    "do not elaborate, pad, or add explanations. Titles and headings must stay short "
    "enough to fit one visual line when the source is one line. "
    "When a character budget is given, treat it as a hard upper bound. "
    "IMPORTANT — mathematics: never translate, rewrite, or invent equations, formulas, "
    "LaTeX, or math variables. Leave symbols such as x_t, A, B, d_k, softmax(...), "
    "fractions, and equation numbers exactly as in the source. "
    "Do NOT wrap variables in $...$ or $$...$$ unless those delimiters already appear "
    "in the source. If the source only introduces an equation in prose without the "
    "formula body, translate the prose only — do not fabricate the formula. "
    "IMPORTANT — people: never translate author names or personal names; keep Latin "
    "spellings exactly. Affiliation institution names may be translated, but person "
    "names must stay unchanged. "
    "If the input is only links, affiliations, or author names, translate labels only and "
    "keep proper nouns/URLs as-is. Do not add explanations. Output translation only."
)

_WS_RE = re.compile(r"\s+")


def estimate_source_lines(text: str, bbox_h: float = 0.0, font_size: float = 0.0) -> int:
    """Rough line count from PDF bbox height (ignore soft wraps in extracted text)."""
    raw = soft_unwrap(text or "")
    if not raw:
        return 1
    by_nl = raw.count("\n") + 1
    fs = font_size if font_size > 0 else 11.0
    if bbox_h > 0:
        by_box = max(1, int(round(bbox_h / max(fs * 1.2, 8.0))))
        if abs(by_box - by_nl) <= 1:
            return max(by_box, by_nl)
        return max(1, min(max(by_box, by_nl), by_box + by_nl))
    return by_nl


def translation_char_budget(
    text: str,
    *,
    block_type: str = "text",
    bbox_h: float = 0.0,
    font_size: float = 0.0,
) -> int:
    """Max Simplified-Chinese characters that should still fit the source seat.

    Never shrink overlay fonts — keep translations short instead.
    """
    raw = soft_unwrap(text or "")
    if not raw:
        return 0
    n = len(raw)
    lines = estimate_source_lines(raw, bbox_h, font_size)
    per_line = max(6, int((n + lines - 1) / lines))
    capacity = per_line * lines

    kind = (block_type or "text").lower()
    if kind in ("title", "heading") or lines <= 1:
        # One visual line: allow a bit more Chinese than the English source.
        return max(6, min(int(n * 1.18) + 4, capacity + 6, n + 20))
    if kind == "caption" or lines <= 2:
        return max(10, min(int(n * 1.22) + 6, int(capacity * 1.12) + 8))
    # Body / meta: slightly generous — Chinese often needs a bit more room.
    return max(16, min(int(n * 1.3) + 12, int(capacity * 1.2) + 16))


def _build_user_prompt(text: str, budget: int) -> str:
    src_n = len((text or "").strip())
    return (
        f"Translate into concise Simplified Chinese. "
        f"Hard limit: at most {budget} Chinese characters "
        f"(source length {src_n}; do not exceed the limit). "
        f"Prefer compact wording over completeness of flourish. "
        f"Output the translation only.\n\n{text}"
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
    max_chars: int | None = None,
) -> str:
    budget = max_chars if max_chars and max_chars > 0 else translation_char_budget(text)
    plain = soft_unwrap(text)
    user_content = _build_user_prompt(plain, budget) if budget else plain
    try:
        out = await chat_completion(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            is_full_url=is_full_url,
            temperature=0.2,
        )
    except ChatAuthError as exc:
        raise TranslateAuthError(str(exc)) from exc

    cleaned = soft_unwrap(out or "")
    # One shorten pass for titles/short seats that still overshoot badly.
    if budget and len(_WS_RE.sub("", cleaned)) > int(budget * 1.25) + 4:
        try:
            shortened = await chat_completion(
                base_url,
                api_key,
                model,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Rewrite this Simplified Chinese academic translation so it has "
                            f"at most {budget} characters. Keep meaning; drop filler. "
                            f"Output translation only.\n\n{cleaned}"
                        ),
                    },
                ],
                is_full_url=is_full_url,
                temperature=0.1,
            )
            if (shortened or "").strip():
                cleaned = shortened.strip()
        except ChatAuthError as exc:
            raise TranslateAuthError(str(exc)) from exc
        except Exception:  # noqa: BLE001
            pass
    return cleaned

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

    # Heal mid-paragraph splits before translating.
    repair_wrapped_paragraph_blocks(db, job.document_id)

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
    # Repair: equation fragments → formula_skip; authors → Latin meta;
    # strip invented LaTeX from existing translations so PDF formulas show through.
    for b in blocks:
        if is_formula_like_text(b.text):
            b.block_type = "formula_skip"
            if b.translation and not b.translation.edited:
                db.delete(b.translation)
            continue
        if is_author_line_text(b.text):
            b.block_type = "meta"
            if b.translation and not b.translation.edited:
                b.translation.text = b.text
                b.translation.status = "done"
            elif not b.translation:
                db.add(
                    Translation(
                        id=str(uuid.uuid4()),
                        block_id=b.id,
                        provider_profile=provider.name,
                        model=provider.model,
                        text=b.text,
                        edited=False,
                        status="done",
                    )
                )
            continue
        if b.translation and b.translation.text and not b.translation.edited:
            cleaned = sanitize_math_translation(b.text, b.translation.text)
            if cleaned != b.translation.text:
                if cleaned.strip():
                    b.translation.text = cleaned
                    b.translation.status = "done"
                else:
                    # Fabricated-only math — drop so the block retranslates as prose.
                    db.delete(b.translation)
    db.commit()

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
            # Equation fragments: keep PDF glyphs — do not overlay a (wrong) translation.
            if is_formula_like_text(block.text):
                block.block_type = "formula_skip"
                if block.translation and not block.translation.edited:
                    db.delete(block.translation)
                job.done += 1
                db.commit()
                continue

            # Author lists: keep Latin names exactly.
            if is_author_line_text(block.text):
                block.block_type = "meta"
                translated = block.text
            else:
                bbox_h = float(block.bbox_y1 - block.bbox_y0)
                budget = translation_char_budget(
                    block.text,
                    block_type=block.block_type or "text",
                    bbox_h=bbox_h,
                    font_size=float(block.font_size or 0),
                )
                translated = await translate_text(
                    provider.base_url,
                    api_key or "ollama",
                    provider.model,
                    block.text,
                    is_full_url=bool(provider.is_full_url),
                    max_chars=budget,
                )
                raw_translated = translated
                translated = sanitize_math_translation(block.text, translated)
                # Do not leave long prose blocks empty when the sanitizer was
                # too aggressive — fall back to the model output (soft-unwrapped).
                if not (translated or "").strip() and len(soft_unwrap(block.text)) > 80:
                    translated = soft_unwrap(raw_translated)
            consecutive_failures = 0
            if not (translated or "").strip() and not is_author_line_text(block.text):
                # Sanitizer removed fabricated-only math — leave uncovered for retry.
                if block.translation and not block.translation.edited:
                    db.delete(block.translation)
                job.done += 1
                db.commit()
                continue
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
