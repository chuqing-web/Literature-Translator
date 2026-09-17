# Literature Translator Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. User requested immediate inline execution.

**Goal:** Ship a local Literature Translator service (Vue 3 + FastAPI + SQLite) with layout-preserving PDF bilingual reading, library, notes, and OpenAI-compatible multi-model config.

**Architecture:** PyMuPDF bbox extraction + pdf.js overlay; FastAPI owns files/DB/LLM; Vue owns reader UX (embedded default, side-by-side toggle).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PyMuPDF, httpx, Vue 3, Vite, pdfjs-dist, SQLite

---

## File map

```
apps/api/
  pyproject.toml / requirements.txt
  app/main.py
  app/config.py
  app/db.py
  app/models.py
  app/schemas.py
  app/services/pdf_parse.py
  app/services/translate.py
  app/services/crypto_settings.py
  app/routers/documents.py
  app/routers/translate.py
  app/routers/notes.py
  app/routers/settings.py
  tests/
apps/web/
  package.json
  src/main.ts
  src/App.vue
  src/router.ts
  src/api/client.ts
  src/views/LibraryView.vue
  src/views/ReaderView.vue
  src/views/SettingsView.vue
  src/components/PdfPage.vue
  src/components/TranslationOverlay.vue
  src/components/NotesPanel.vue
  src/stores/reader.ts
  src/styles/theme.css
data/                 # runtime, gitignored
README.md
.gitignore
```

---

### Task 1: Repository scaffold

**Files:**
- Create: `.gitignore`, `README.md`, `apps/api/requirements.txt`, `apps/api/app/__init__.py`, `apps/api/app/main.py`, `apps/api/app/config.py`, `apps/web/package.json`, Vite Vue TS skeleton

- [ ] **Step 1:** Create `.gitignore` (node_modules, data/, __pycache__, .env, dist)
- [ ] **Step 2:** Create FastAPI hello + CORS + `/api/health`
- [ ] **Step 3:** Create Vue 3 + Vite app with router stubs (Library / Reader / Settings)
- [ ] **Step 4:** README with start commands for api and web
- [ ] **Step 5:** Verify `uvicorn` health and `npm run dev` load

### Task 2: DB models + document upload

**Files:**
- Create: `apps/api/app/db.py`, `models.py`, `schemas.py`, `routers/documents.py`

- [ ] **Step 1:** SQLAlchemy models for documents, blocks, translations, notes, highlights, settings, provider_profiles
- [ ] **Step 2:** `POST /api/documents` multipart upload → save PDF under `data/library/`
- [ ] **Step 3:** `GET /api/documents`, `GET /api/documents/{id}`, `DELETE`, `GET /api/documents/{id}/file`
- [ ] **Step 4:** pytest upload + list

### Task 3: PDF bbox parse service

**Files:**
- Create: `apps/api/app/services/pdf_parse.py`
- Modify: `routers/documents.py` add `POST /{id}/parse`

- [ ] **Step 1:** PyMuPDF extract per-page blocks with bbox + reading order
- [ ] **Step 2:** Heuristic skip empty / tiny; mark likely-scan if almost no text
- [ ] **Step 3:** Persist blocks; set document status `ready` | `unsupported_scan` | `error`
- [ ] **Step 4:** `GET /api/documents/{id}/pages/{page}/blocks`
- [ ] **Step 5:** pytest with a tiny fixture PDF

### Task 4: OpenAI-compatible translation

**Files:**
- Create: `apps/api/app/services/translate.py`, `routers/translate.py`, `routers/settings.py`, `services/crypto_settings.py`

- [ ] **Step 1:** Provider profile CRUD; default settings
- [ ] **Step 2:** Batch translate untranslated text blocks (paragraph prompt, preserve meaning, academic Chinese)
- [ ] **Step 3:** Job status endpoint; `PATCH` edited translation
- [ ] **Step 4:** pytest with httpx mock

### Task 5: Vue library + settings UI

**Files:**
- Create: `LibraryView.vue`, `SettingsView.vue`, `api/client.ts`, theme CSS

- [ ] **Step 1:** Library list, upload button, open reader
- [ ] **Step 2:** Settings: base_url, api_key, model, save profile
- [ ] **Step 3:** Wire API client to localhost:8787

### Task 6: Reader — pdf.js + overlay + dual view modes

**Files:**
- Create: `ReaderView.vue`, `PdfPage.vue`, `TranslationOverlay.vue`, `stores/reader.ts`

- [ ] **Step 1:** Load PDF via `/file` into pdf.js
- [ ] **Step 2:** Fetch blocks; render translation under blocks (embedded mode)
- [ ] **Step 3:** Side-by-side mode with sync scroll
- [ ] **Step 4:** Trigger translate; poll status; refresh overlays
- [ ] **Step 5:** Inline edit translation → PATCH

### Task 7: Notes + highlights (M3)

**Files:**
- Create: `routers/notes.py`, `NotesPanel.vue`

- [ ] **Step 1:** CRUD notes/highlights API
- [ ] **Step 2:** Select block → highlight; notes panel list/add/delete

### Task 8: Polish + Word export stub (M4 partial)

- [ ] **Step 1:** Typography settings applied to overlay CSS variables
- [ ] **Step 2:** Export translated text to `.docx` via python-docx (sequential by page/block; best-effort)

---

## Execution order

Do Tasks 1→6 for a usable M1+M2 demo, then 7–8.

## Spec coverage

| Spec item | Tasks |
|-----------|-------|
| Local web service | 1 |
| SQLite + library files | 2 |
| Bbox parse + scan detect | 3 |
| OpenAI-compatible translate | 4 |
| Library + settings UI | 5 |
| Embedded + side-by-side reader | 6 |
| Notes/highlights | 7 |
| Typography + Word export | 8 |
| No brand name in code | all |
---
