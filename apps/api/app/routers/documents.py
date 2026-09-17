from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Block, Document
from app.schemas import DocumentOut
from app.services.pdf_parse import parse_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    doc_id = str(uuid.uuid4())
    safe_name = Path(file.filename).name
    dest = settings.library_dir / f"{doc_id}.pdf"
    content = await file.read()
    dest.write_bytes(content)

    document = Document(
        id=doc_id,
        title=safe_name.rsplit(".", 1)[0],
        filename=safe_name,
        path=str(dest),
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    parse_document(db, document)
    db.refresh(document)
    return document


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    return document


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    path = Path(document.path)
    db.delete(document)
    db.commit()
    if path.exists():
        path.unlink(missing_ok=True)
    return {"status": "deleted"}


@router.get("/{document_id}/file")
def get_file(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    path = Path(document.path)
    if not path.exists():
        raise HTTPException(404, "PDF file missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.filename,
        content_disposition_type="inline",
    )


@router.post("/{document_id}/parse", response_model=DocumentOut)
def reparse(document_id: str, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    parse_document(db, document)
    db.refresh(document)
    return document


@router.get("/{document_id}/blocks/{block_id}/preview.png")
def block_preview(
    document_id: str,
    block_id: str,
    scale: float = Query(2.0, ge=1.0, le=3.5),
    db: Session = Depends(get_db),
) -> Response:
    """Render a block's PDF bbox as PNG (figures / tables / visual placeholders)."""
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    block = (
        db.query(Block)
        .filter(Block.id == block_id, Block.document_id == document_id)
        .first()
    )
    if not block:
        raise HTTPException(404, "Block not found")

    path = Path(document.path)
    if not path.exists():
        raise HTTPException(404, "PDF file missing on disk")

    try:
        pdf = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Failed to open PDF: {exc}") from exc

    try:
        if block.page_index < 0 or block.page_index >= pdf.page_count:
            raise HTTPException(404, "Page out of range")
        page = pdf[block.page_index]
        pad = 2.0
        clip = pymupdf.Rect(
            max(0.0, block.bbox_x0 - pad),
            max(0.0, block.bbox_y0 - pad),
            min(float(page.rect.width), block.bbox_x1 + pad),
            min(float(page.rect.height), block.bbox_y1 + pad),
        )
        if clip.width < 4 or clip.height < 4:
            raise HTTPException(400, "Block region too small")
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        return Response(
            content=pix.tobytes("png"),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    finally:
        pdf.close()
