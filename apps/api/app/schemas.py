from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    title: str
    filename: str
    page_count: int
    status: str
    status_message: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlockOut(BaseModel):
    id: str
    page_index: int
    block_index: int
    text: str
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    block_type: str
    font_size: float = 0
    page_width: float
    page_height: float
    translation: str | None = None
    translation_edited: bool = False
    translation_status: str | None = None

    model_config = {"from_attributes": True}


class TranslationUpdate(BaseModel):
    text: str


class ProviderIn(BaseModel):
    name: str = "Default"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    is_default: bool = True
    is_full_url: bool = False


class ProviderOut(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    is_default: bool
    has_api_key: bool
    is_full_url: bool = False
    resolved_url: str = ""

    model_config = {"from_attributes": True}


class ProviderTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: int = 0
    sample: str | None = None
    resolved_url: str = ""


class ProviderPresetOut(BaseModel):
    id: str
    name: str
    base_url: str
    model: str


class UrlPreviewIn(BaseModel):
    base_url: str
    is_full_url: bool = False


class UrlPreviewOut(BaseModel):
    resolved_url: str
    mode: str


class NoteIn(BaseModel):
    page_index: int = 0
    block_id: str | None = None
    content: str
    color: str = "#f6e58d"


class NoteOut(BaseModel):
    id: str
    document_id: str
    page_index: int
    block_id: str | None
    content: str
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HighlightIn(BaseModel):
    page_index: int = 0
    block_id: str
    color: str = "#74b9ff"


class HighlightOut(BaseModel):
    id: str
    document_id: str
    page_index: int
    block_id: str
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SettingsOut(BaseModel):
    view_mode: str = "embedded"
    font_family: str = "Source Han Serif SC, Noto Serif SC, serif"
    font_size: int = 14
    line_height: float = 1.6
    active_provider_id: str | None = None
    locale: str = "zh"


class SettingsUpdate(BaseModel):
    view_mode: str | None = None
    font_family: str | None = None
    font_size: int | None = None
    line_height: float | None = None
    active_provider_id: str | None = None
    locale: str | None = None


class TranslateJobOut(BaseModel):
    id: str
    document_id: str
    status: str
    total: int
    done: int
    error: str = ""

    model_config = {"from_attributes": True}


class JobStartOut(BaseModel):
    job: TranslateJobOut


class HealthOut(BaseModel):
    status: str = "ok"
    app: str
    extras: dict[str, Any] = Field(default_factory=dict)


class AssistantMessageOut(BaseModel):
    id: str
    role: str
    content: str
    context_mode: str | None = None
    page_index: int | None = None
    block_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssistantThreadOut(BaseModel):
    thread_id: str
    messages: list[AssistantMessageOut]


class AssistantChatIn(BaseModel):
    content: str
    context_mode: str = "auto"  # auto | block | page | full
    page_index: int = 0
    block_id: str | None = None


class AssistantChatOut(BaseModel):
    thread_id: str
    user_message: AssistantMessageOut
    assistant_message: AssistantMessageOut
