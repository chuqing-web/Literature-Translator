# Literature Translator — Design Spec

**Date:** 2026-09-17  
**Product name:** Literature Translator（文献译读）  
**Constraint:** Product UI, code, comments, and docs must not contain the reference product’s Chinese brand name.

## Goal

A local-first academic PDF bilingual reading service: upload papers, preserve page layout via bbox text blocks, translate with OpenAI-compatible models, read in embedded or side-by-side modes, manage a local library, take highlights/notes, and configure translation providers — all on `localhost`, data on disk.

## Non-goals (this version)

- Cloud accounts / multi-user sync
- Scanned-PDF OCR pipeline (detect & show “not supported” message)
- Marketplace / plugins

## Architecture

- **Backend:** Python FastAPI + SQLite (`data/lit.db`) + files under `data/library/`
- **Frontend:** Vue 3 + Vite + pdf.js
- **PDF strategy:** PyMuPDF extracts ordered text blocks with bounding boxes; frontend renders original PDF with pdf.js and overlays / mirrors translations by block coordinates
- **Translation:** Single OpenAI-compatible HTTP adapter (`base_url`, `api_key`, `model`)

```
Browser (Vue)  --REST-->  FastAPI
                            |-- SQLite (meta, blocks, translations, notes, settings)
                            |-- data/library/{doc_id}.pdf
                            |-- OpenAI-compatible LLM API
```

## Data model (SQLite)

- `documents` — id, title, filename, path, page_count, status, created_at, updated_at
- `blocks` — id, document_id, page_index, block_index, text, bbox_x0/y0/x1/y1, block_type (`text`|`caption`|`formula_skip`)
- `translations` — id, block_id, provider_profile, model, text, edited (bool), updated_at
- `notes` — id, document_id, page_index, anchor (block_id or bbox JSON), content, color, created_at
- `highlights` — id, document_id, page_index, block_id, color, created_at
- `settings` — key/value JSON (active provider profile, typography, view mode default)
- `provider_profiles` — id, name, base_url, api_key_enc, model, is_default

API keys stored locally only; obfuscate at rest (Fernet with machine-local key file under `data/`).

## Reader UX

1. **Default: embedded** — under each text block on the page, show Chinese translation (custom font/size/line-height)
2. **Side-by-side** — left: original PDF; right: translation page with same page size and block positions; synchronized scroll
3. Editable translation text; edits persist to `translations.edited`
4. Notes panel on the side; highlights on source blocks without breaking overlay layout
5. Figures/formulas: keep visual from PDF; skip formula-like blocks when detectable; translate captions as separate blocks

## API surface (high level)

- `GET/POST /api/documents`, `GET /api/documents/{id}`, `DELETE /api/documents/{id}`
- `POST /api/documents/{id}/parse`
- `GET /api/documents/{id}/pages/{n}/blocks`
- `POST /api/documents/{id}/translate` (async job) + `GET .../translate/status`
- `PATCH /api/blocks/{id}/translation`
- `CRUD /api/documents/{id}/notes|highlights`
- `CRUD /api/providers`, `GET/PUT /api/settings`
- `GET /api/documents/{id}/file` — stream PDF

## Milestones

| M | Deliverable |
|---|-------------|
| M1 | Scaffold, upload, parse bbox blocks, pdf.js reader, embed + side-by-side, one-shot translate via compatible API |
| M2 | Local library UI (list/search/delete), document status, reopen last view |
| M3 | Highlight + notes panel, persist & show on reader |
| M4 | Multi provider profiles, typography settings, Word export (best-effort structure) |

## Error handling

- Parse failure → document status `error` with message
- Empty text PDF / likely scan → status `unsupported_scan`
- Translate failures per-block retry once; mark failed blocks

## Testing

- API: pytest for parse block ordering, translation persistence, settings
- Frontend: Vitest smoke for view-mode store; manual PDF fixture for reader
---
