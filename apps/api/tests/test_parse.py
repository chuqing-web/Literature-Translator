from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import Document
from app.services.pdf_parse import parse_document


def test_parse_sample_pdf():
    init_db()
    sample = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample.pdf"
    assert sample.exists()
    db = SessionLocal()
    try:
        doc = Document(
            id="test-sample-doc",
            title="sample",
            filename="sample.pdf",
            path=str(sample),
            status="uploaded",
        )
        db.merge(doc)
        db.commit()
        doc = db.get(Document, "test-sample-doc")
        assert doc is not None
        result = parse_document(db, doc)
        assert result.status == "ready"
        assert result.block_count >= 2
        assert result.page_count == 1
    finally:
        db.close()
