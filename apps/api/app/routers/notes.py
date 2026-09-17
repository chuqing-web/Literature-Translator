from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document, Highlight, Note
from app.schemas import HighlightIn, HighlightOut, NoteIn, NoteOut

router = APIRouter(prefix="/api/documents/{document_id}", tags=["notes"])


def _doc(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    return document


@router.get("/notes", response_model=list[NoteOut])
def list_notes(document_id: str, db: Session = Depends(get_db)) -> list[Note]:
    _doc(db, document_id)
    return (
        db.query(Note)
        .filter(Note.document_id == document_id)
        .order_by(Note.created_at.desc())
        .all()
    )


@router.post("/notes", response_model=NoteOut)
def create_note(document_id: str, body: NoteIn, db: Session = Depends(get_db)) -> Note:
    _doc(db, document_id)
    note = Note(
        id=str(uuid.uuid4()),
        document_id=document_id,
        page_index=body.page_index,
        block_id=body.block_id,
        content=body.content,
        color=body.color,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}")
def delete_note(document_id: str, note_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    note = db.get(Note, note_id)
    if not note or note.document_id != document_id:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
    return {"status": "deleted"}


@router.get("/highlights", response_model=list[HighlightOut])
def list_highlights(document_id: str, db: Session = Depends(get_db)) -> list[Highlight]:
    _doc(db, document_id)
    return db.query(Highlight).filter(Highlight.document_id == document_id).all()


@router.post("/highlights", response_model=HighlightOut)
def create_highlight(
    document_id: str, body: HighlightIn, db: Session = Depends(get_db)
) -> Highlight:
    _doc(db, document_id)
    hl = Highlight(
        id=str(uuid.uuid4()),
        document_id=document_id,
        page_index=body.page_index,
        block_id=body.block_id,
        color=body.color,
    )
    db.add(hl)
    db.commit()
    db.refresh(hl)
    return hl


@router.delete("/highlights/{highlight_id}")
def delete_highlight(
    document_id: str, highlight_id: str, db: Session = Depends(get_db)
) -> dict[str, str]:
    hl = db.get(Highlight, highlight_id)
    if not hl or hl.document_id != document_id:
        raise HTTPException(404, "Highlight not found")
    db.delete(hl)
    db.commit()
    return {"status": "deleted"}
