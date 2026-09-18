from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import Document
from app.services.pdf_parse import _RawBlock, _merge_fragments, parse_document


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


def test_merge_first_line_into_following_paragraph():
    first = _RawBlock(
        70.4,
        297.8,
        541.1,
        308.0,
        "We employ a data engine to generate training data by using our model in the loop with annotators to",
        "text",
        10.0,
    )
    rest = _RawBlock(
        70.9,
        309.8,
        542.5,
        415.4,
        "interactively annotate new and challenging data. Different from most existing video segmentation datasets,",
        "text",
        10.0,
    )
    merged = _merge_fragments([first, rest])
    assert len(merged) == 1
    assert merged[0].text.startswith("We employ a data engine")
    assert "interactively annotate" in merged[0].text
    assert merged[0].y0 == 297.8
    assert merged[0].y1 == 415.4


def test_does_not_merge_across_sentence_break():
    a = _RawBlock(70, 100, 300, 140, "This paragraph ends here.", "text", 10)
    b = _RawBlock(70, 156, 300, 200, "A new paragraph starts.", "text", 10)
    assert len(_merge_fragments([a, b])) == 2
