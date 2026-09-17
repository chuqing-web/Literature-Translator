from types import SimpleNamespace

from app.services.chat import (
    FULL_CHAR_LIMIT,
    PAGE_CHAR_LIMIT,
    BuiltContext,
    _join_blocks,
    build_paper_context,
    format_context_message,
)


def _block(text: str, page=0, idx=0, block_type="text", translation=None, bid="b1"):
    tr = SimpleNamespace(text=translation) if translation else None
    return SimpleNamespace(
        id=bid,
        text=text,
        page_index=page,
        block_index=idx,
        block_type=block_type,
        translation=tr,
    )


def test_join_blocks_includes_translation():
    blocks = [_block("Hello world", translation="你好世界")]
    text, truncated = _join_blocks(blocks, PAGE_CHAR_LIMIT)
    assert "Hello world" in text
    assert "[译] 你好世界" in text
    assert not truncated


def test_join_blocks_skips_non_text():
    blocks = [_block("skip me", block_type="formula_skip"), _block("keep")]
    text, _ = _join_blocks(blocks, PAGE_CHAR_LIMIT)
    assert "keep" in text
    assert "skip me" not in text


def test_join_blocks_truncates():
    blocks = [_block("a" * 100, idx=i, bid=f"b{i}") for i in range(5)]
    text, truncated = _join_blocks(blocks, 150)
    assert truncated
    assert "truncated" in text


def test_format_context_message():
    doc = SimpleNamespace(title="My Paper", filename="x.pdf")
    ctx = BuiltContext(mode="page", label="current page · page 1", text="Body", page_index=0, block_id=None)
    out = format_context_message(doc, ctx)
    assert "My Paper" in out
    assert "current page · page 1" in out
    assert "Body" in out


class _FakeQuery:
    def __init__(self, items):
        self._items = items

    def options(self, *_a, **_k):
        return self

    def filter(self, *criteria):
        # Very small fake: ignore SQLAlchemy criteria objects, filter in Python when possible
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _FakeDB:
    def __init__(self, by_id=None, page_blocks=None, all_blocks=None):
        self.by_id = by_id or {}
        self.page_blocks = page_blocks or []
        self.all_blocks = all_blocks or []
        self._mode = "all"

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Block" or "Block" in str(model):
            # Heuristic: callers either look up by id (first) or list
            if self.by_id and not self.page_blocks and not self.all_blocks:
                return _FakeQuery(list(self.by_id.values()))
            if self.all_blocks and not self.page_blocks:
                return _FakeQuery(self.all_blocks)
            return _FakeQuery(self.page_blocks or self.all_blocks or list(self.by_id.values()))
        return _FakeQuery([])


def test_build_context_full():
    blocks = [_block(f"p{i}", page=i, idx=0, bid=f"b{i}") for i in range(3)]
    db = _FakeDB(all_blocks=blocks)
    doc = SimpleNamespace(id="d1", title="T", filename="f.pdf")
    # Patch filter behavior by using a smarter fake
    class SmartDB(_FakeDB):
        def query(self, model):
            return _FakeQuery(self.all_blocks)

    ctx = build_paper_context(SmartDB(all_blocks=blocks), doc, context_mode="full", page_index=0, block_id=None)
    assert ctx.mode == "full"
    assert "p0" in ctx.text and "p2" in ctx.text


def test_build_context_block_preferred():
    block = _block("Selected", page=2, bid="sel")
    class SmartDB:
        def query(self, model):
            class Q:
                def options(self, *a, **k):
                    return self
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return block
                def all(self):
                    return [block]
            return Q()

    doc = SimpleNamespace(id="d1", title="T", filename="f.pdf")
    ctx = build_paper_context(SmartDB(), doc, context_mode="auto", page_index=0, block_id="sel")
    assert ctx.mode == "block"
    assert ctx.block_id == "sel"
    assert "Selected" in ctx.text


def test_limits_constants():
    assert PAGE_CHAR_LIMIT == 12_000
    assert FULL_CHAR_LIMIT == 40_000
