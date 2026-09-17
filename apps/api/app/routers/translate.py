from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db import SessionLocal, get_db
from app.models import Block, Document, TranslateJob, Translation
from app.schemas import BlockOut, JobStartOut, TranslateJobOut, TranslationUpdate
from app.services.translate import run_translate_job

router = APIRouter(prefix="/api", tags=["translate"])


def _block_out(block: Block) -> BlockOut:
    tr = block.translation
    return BlockOut(
        id=block.id,
        page_index=block.page_index,
        block_index=block.block_index,
        text=block.text,
        bbox_x0=block.bbox_x0,
        bbox_y0=block.bbox_y0,
        bbox_x1=block.bbox_x1,
        bbox_y1=block.bbox_y1,
        block_type=block.block_type,
        font_size=float(getattr(block, "font_size", 0) or 0),
        page_width=block.page_width,
        page_height=block.page_height,
        translation=tr.text if tr and tr.text else None,
        translation_edited=bool(tr.edited) if tr else False,
        translation_status=tr.status if tr else None,
    )


@router.get("/documents/{document_id}/pages/{page_index}/blocks", response_model=list[BlockOut])
def page_blocks(
    document_id: str,
    page_index: int,
    db: Session = Depends(get_db),
) -> list[BlockOut]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    blocks = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(Block.document_id == document_id, Block.page_index == page_index)
        .order_by(Block.block_index)
        .all()
    )
    return [_block_out(b) for b in blocks]


@router.get("/documents/{document_id}/blocks", response_model=list[BlockOut])
def all_blocks(document_id: str, db: Session = Depends(get_db)) -> list[BlockOut]:
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
    return [_block_out(b) for b in blocks]


def _run_job_sync(job_id: str) -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_translate_job(db, job_id))
    finally:
        db.close()


@router.post("/documents/{document_id}/translate", response_model=JobStartOut)
def start_translate(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobStartOut:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    if document.status == "unsupported_scan":
        raise HTTPException(400, document.status_message or "Scanned PDF not supported")

    job = TranslateJob(
        id=str(uuid.uuid4()),
        document_id=document_id,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job_sync, job.id)
    return JobStartOut(job=TranslateJobOut.model_validate(job))


@router.get("/translate/jobs/{job_id}", response_model=TranslateJobOut)
def job_status(job_id: str, db: Session = Depends(get_db)) -> TranslateJob:
    job = db.get(TranslateJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.patch("/blocks/{block_id}/translation", response_model=BlockOut)
def update_translation(
    block_id: str,
    body: TranslationUpdate,
    db: Session = Depends(get_db),
) -> BlockOut:
    block = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(Block.id == block_id)
        .first()
    )
    if not block:
        raise HTTPException(404, "Block not found")
    if block.translation:
        block.translation.text = body.text
        block.translation.edited = True
        block.translation.status = "done"
    else:
        db.add(
            Translation(
                id=str(uuid.uuid4()),
                block_id=block.id,
                text=body.text,
                edited=True,
                status="done",
            )
        )
    db.commit()
    db.refresh(block)
    block = (
        db.query(Block)
        .options(joinedload(Block.translation))
        .filter(Block.id == block_id)
        .first()
    )
    assert block is not None
    return _block_out(block)
