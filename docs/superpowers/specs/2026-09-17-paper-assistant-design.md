# Paper Assistant (论文助手) Design

**Date:** 2026-09-17  
**Status:** Approved for implementation

## Goal

Add a **论文助手** tab beside notes in the reader right sidebar. Users can chat about the paper (DeepSeek-like continuous thread), with context defaulting to the selected block, falling back to the current page, and optionally switching to the full document. One conversation thread per paper, persisted on the server.

## Non-goals

- Multiple threads per document
- Streaming responses (v1 is request/response; streaming can follow)
- Vision / figure understanding
- Embedding / RAG search
- Separate full-page chat route

## Architecture

```
ReaderView
  aside.notes-rail
    tab bar: 笔记 | 论文助手
    NotesPanel | AssistantPanel
         │
         ▼
  POST/GET /api/documents/{id}/assistant/...
         │
  AssistantThread (1:1 document) + AssistantMessage[]
         │
  build_context(block|page|full) + chat_completion(provider)
```

Reuse the existing default OpenAI-compatible provider (`get_default_provider`, encrypted keys, URL helpers). Extract a shared `chat_completion(messages, …)` used by translation and assistant.

## Data model

### `assistant_threads`

| Column | Type | Notes |
|--------|------|--------|
| id | string PK | uuid |
| document_id | string FK unique | one thread per document |
| created_at | datetime | |
| updated_at | datetime | |

### `assistant_messages`

| Column | Type | Notes |
|--------|------|--------|
| id | string PK | uuid |
| thread_id | string FK | cascade delete |
| role | string | `user` \| `assistant` \| `system` (system not stored for history replay; only user/assistant persisted) |
| content | string | message text |
| context_mode | string nullable | for user msgs: `block` \| `page` \| `full` |
| page_index | int nullable | |
| block_id | string nullable | |
| created_at | datetime | |

Document delete cascades to thread → messages.

## API

Prefix: `/api/documents/{document_id}/assistant`

### `GET /messages`

Returns `{ thread_id, messages: AssistantMessageOut[] }` ordered by `created_at`. Creates an empty thread if none exists.

### `POST /chat`

Body:

```json
{
  "content": "这段在说什么？",
  "context_mode": "auto",
  "page_index": 0,
  "block_id": "optional-uuid"
}
```

- `context_mode`: `auto` \| `full`
  - `auto`: if `block_id` present and valid → block context; else page context for `page_index`
  - `full`: all text blocks (capped)
- Persists user message, builds LLM messages, calls provider, persists assistant reply, returns both new messages (or full reply payload with assistant message).

### `DELETE /messages` (optional clear)

Clears all messages in the thread (keeps thread). Useful for “清空对话”.

Errors: 404 document; 400 empty content; 503 no provider configured; 401/403 from provider mapped to clear error (reuse `TranslateAuthError` pattern).

## Context assembly

Server builds a system prompt:

> You are a paper-reading assistant. Help the user understand the scholarly paper. Answer in the user’s language (default Simplified Chinese if unclear). Be precise; quote or paraphrase the paper when helpful. Do not invent citations or results not in the provided context.

Then a context block:

```
[Document title]
[Context scope: selected passage | page N | full document]
---
{text}
(optional translation lines when available)
```

Limits:

- Block: full block text + translation if any
- Page: concatenate text blocks on that page, max ~12k chars
- Full: all pages’ text blocks in order, max ~40k chars (truncate with notice)

Chat history: last N messages (e.g. 40 turns of user+assistant) sent with the request. Context snippet is attached to the **current** user turn (or as a separate system/user preamble), not re-stored as a visible chat bubble beyond a small “引用：第 x 页选区” hint in the UI for that user message.

## UI / UX

### Rail tabs

Top of `.notes-rail`: segmented control **笔记** | **论文助手**. Persist active tab in component state only (session). Default: 笔记 (unchanged habit) or 论文助手 if we prefer discovery—**default 笔记**.

### AssistantPanel (DeepSeek-like)

1. Header: title + optional clear button
2. Context strip: shows effective scope (“选中段落 · 第 3 页” / “当前页 · 第 3 页” / “全文”) + toggle **全文** on/off (when off → auto)
3. Scrollable message list (user right-aligned or distinct bubble; assistant left)
4. Input: textarea + send; Enter to send, Shift+Enter newline
5. Loading state while waiting; disable send
6. Empty state: short hint to select a block or ask about the page

Parent `ReaderView` owns API calls and passes `messages`, `sending`, `contextHint`, `useFullDoc`.

Widen `.notes-rail` slightly when assistant tab is active if needed (e.g. 300px), keep layout consistent with theme.

### i18n

Add zh/en keys for tab labels, hints, placeholders, errors, clear confirm.

## Frontend API client

Types: `AssistantMessageItem`, `AssistantChatResponse`.  
Methods: `listAssistantMessages(docId)`, `chatAssistant(docId, body)`, `clearAssistantMessages(docId)`.

## Error handling

- No provider: show settings CTA message in panel
- Network/provider failure: keep user message in DB or roll back? **Keep user message, show error bubble or toast, allow retry** (retry = resend same content as new turn is fine for v1; simpler: on failure do not commit user message—transactional). Prefer **atomic**: only commit user+assistant after success; on failure return error and do not persist. Client keeps draft or shows error.

## Testing

- Unit: context builder (block / page / full truncation)
- API: get creates thread; chat persists two messages; clear empties; 404 missing doc
- Manual: tab switch, select block → hint updates, toggle full, reload page restores history

## File touch list

| Area | Files |
|------|--------|
| Models/schemas | `apps/api/app/models.py`, `schemas.py` |
| Service | `apps/api/app/services/chat.py` (new), refactor `translate.py` to use shared completion |
| Router | `apps/api/app/routers/assistant.py` (new), register in `main.py` |
| Tests | `apps/api/tests/test_assistant_context.py`, `test_assistant_api.py` |
| Web | `AssistantPanel.vue`, `ReaderView.vue`, `client.ts`, `i18n/messages.ts`, `theme.css` |
