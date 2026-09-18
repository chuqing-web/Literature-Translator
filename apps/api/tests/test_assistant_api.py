import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Block, Document


def _seed_doc() -> str:
    init_db()
    doc_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(
            Document(
                id=doc_id,
                title="Assist Paper",
                filename="a.pdf",
                path="x",
                page_count=1,
                status="ready",
            )
        )
        db.add(
            Block(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                page_index=0,
                block_index=0,
                text="Gradient descent minimizes the loss.",
                bbox_x0=0,
                bbox_y0=0,
                bbox_x1=10,
                bbox_y1=10,
                block_type="text",
                page_width=100,
                page_height=100,
            )
        )
        db.commit()
    finally:
        db.close()
    return doc_id


def test_list_messages_creates_empty_thread():
    doc_id = _seed_doc()
    client = TestClient(app)
    res = client.get(f"/api/documents/{doc_id}/assistant/messages")
    assert res.status_code == 200
    data = res.json()
    assert data["thread_id"]
    assert data["messages"] == []


def test_chat_persists_roundtrip():
    doc_id = _seed_doc()
    client = TestClient(app)

    with patch(
        "app.routers.assistant.get_default_provider",
        return_value=type(
            "P",
            (),
            {
                "base_url": "https://example.com/v1",
                "api_key_enc": "",
                "model": "test-model",
                "is_full_url": False,
            },
        )(),
    ), patch(
        "app.routers.assistant.chat_completion",
        new_callable=AsyncMock,
        return_value="这是在讲梯度下降。",
    ), patch("app.routers.assistant.decrypt_secret", return_value=""):
        res = client.post(
            f"/api/documents/{doc_id}/assistant/chat",
            json={"content": "这段什么意思？", "context_mode": "auto", "page_index": 0},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user_message"]["content"] == "这段什么意思？"
    assert body["assistant_message"]["content"] == "这是在讲梯度下降。"
    assert body["user_message"]["context_mode"] == "page"

    listed = client.get(f"/api/documents/{doc_id}/assistant/messages")
    assert listed.status_code == 200
    msgs = listed.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"

    cleared = client.delete(f"/api/documents/{doc_id}/assistant/messages")
    assert cleared.status_code == 200
    listed2 = client.get(f"/api/documents/{doc_id}/assistant/messages")
    assert listed2.json()["messages"] == []


def test_chat_requires_provider():
    doc_id = _seed_doc()
    client = TestClient(app)
    with patch("app.routers.assistant.get_default_provider", return_value=None):
        res = client.post(
            f"/api/documents/{doc_id}/assistant/chat",
            json={"content": "hi", "context_mode": "auto", "page_index": 0},
        )
    assert res.status_code == 503


def test_chat_stream_emits_sse_and_persists():
    doc_id = _seed_doc()
    client = TestClient(app)

    async def fake_stream(*_a, **_k):
        for piece in ("流", "式", "回复"):
            yield piece

    with patch(
        "app.routers.assistant.get_default_provider",
        return_value=type(
            "P",
            (),
            {
                "base_url": "https://example.com/v1",
                "api_key_enc": "",
                "model": "test-model",
                "is_full_url": False,
            },
        )(),
    ), patch(
        "app.routers.assistant.chat_completion_stream",
        new=fake_stream,
    ), patch("app.routers.assistant.decrypt_secret", return_value=""):
        with client.stream(
            "POST",
            f"/api/documents/{doc_id}/assistant/chat/stream",
            json={"content": "讲一下", "context_mode": "page", "page_index": 0},
        ) as res:
            assert res.status_code == 200, res.text
            body = "".join(res.iter_text())

    assert "data: " in body
    assert '"type": "user"' in body or '"type":"user"' in body
    assert '"type": "delta"' in body or '"type":"delta"' in body
    assert '"type": "done"' in body or '"type":"done"' in body
    assert "流式回复" in body

    listed = client.get(f"/api/documents/{doc_id}/assistant/messages")
    msgs = listed.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "流式回复"
