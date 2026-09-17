# Paper Assistant Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Add a persistent per-document paper assistant chat tab beside notes in the reader sidebar.

**Architecture:** Tabbed rail (笔记 | 论文助手); one `AssistantThread` per document; server builds block/page/full context and calls shared OpenAI-compatible chat completion.

**Tech Stack:** FastAPI + SQLAlchemy SQLite, Vue 3 + TypeScript, existing provider stack.

---

### Task 1: Shared chat_completion + context builder

**Files:**
- Create: `apps/api/app/services/chat.py`
- Modify: `apps/api/app/services/translate.py` to call shared helper
- Test: `apps/api/tests/test_assistant_context.py`

### Task 2: Models, schemas, assistant router

**Files:**
- Modify: `apps/api/app/models.py`, `schemas.py`, `main.py`
- Create: `apps/api/app/routers/assistant.py`
- Test: `apps/api/tests/test_assistant_api.py`

### Task 3: Frontend client + AssistantPanel + ReaderView

**Files:**
- Modify: `apps/web/src/api/client.ts`, `ReaderView.vue`, `i18n/messages.ts`, `theme.css`
- Create: `apps/web/src/components/AssistantPanel.vue`
