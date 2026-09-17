# Literature Translator

**Read foreign papers in your language — without losing the page.**

A local-first bilingual PDF reader for researchers, graduate students, and anyone who needs to *understand* academic literature, not just machine-translate it. Upload a paper, keep the original layout, read paragraph-level translations beside the source, annotate as you go, and ask a paper-aware assistant when a method section gets dense.

[English](./README.md) · [中文](./README.zh-CN.md)

---

## Screenshots

### Local library

Upload papers, track ready status, and open any document from your on-disk library.

![Library — local paper collection](./picture/home.png)

### Side-by-side bilingual reading

Original PDF on the left, layout-aligned Chinese translation on the right, with margin notes and Paper Assistant in the rail.

![Reader — side-by-side translation with notes](./picture/reader-demo.png)

---

## Why this exists

Academic PDFs are hostile to translation tools.

Generic translators flatten pages into a wall of text. Figures drift. Equations vanish. Captions stick to the wrong paragraph. You lose the visual map that makes a paper readable — the columns, the callouts, the relationship between a claim and the figure that supports it.

Literature Translator is built for **layout-preserving bilingual reading**:

1. **Parse** the PDF into ordered text blocks with bounding boxes  
2. **Translate** those blocks with any OpenAI-compatible model you choose  
3. **Render** the original page with pdf.js, then place translations where the source lives — embedded under each block, or on a synchronized side-by-side pane  

Your papers stay on disk. Your API keys stay on your machine. The reading studio runs on `localhost`.

---

## Who it’s for

| You are… | You get… |
|----------|----------|
| A researcher skimming non-native papers | Faster comprehension without sacrificing layout |
| A grad student building a reading list | A local library of translated, annotated PDFs |
| A bilingual lab / reading group | Shared workflow: translate → note → discuss |
| Someone who cares about data locality | No cloud account, no upload-to-vendor-by-default |

---

## What you can do

### Layout-aware bilingual reading

- **Embedded mode** — Chinese (or your target language) appears under each source block on the page, with typography you control  
- **Side-by-side mode** — original PDF on the left, translation page on the right; same page size, aligned blocks, synchronized scroll  
- **Block-level edits** — fix a mistranslated sentence; edits persist locally  

Figures and formula-like regions stay as visuals from the PDF. Captions are treated as their own blocks so they can be translated without tearing the page apart.

### Local paper library

- Upload text-based PDFs into a personal library  
- Track parse / translate status per document  
- Reopen last reading position and keep working  

### Highlights, notes & paper assistant

- Highlight source blocks without breaking overlay layout  
- Anchor **margin notes** to a selected block or page  
- Chat with a **Paper Assistant** grounded in the selected passage, the current page, or (optionally) the full document — one continuous thread per paper  

### Your models, your keys

- Connect any **OpenAI-compatible** endpoint (cloud APIs, local gateways, Ollama-style setups)  
- Multiple provider profiles, vendor presets, and a live URL preview  
- Keys encrypted at rest on your machine — never shipped as part of a shared cloud account  

### Export when you need it

- Export bilingual content to **Word (.docx)** for drafting, sharing, or further editing  

---

## How it works

```
Browser (Vue 3 + pdf.js)
        │  REST
        ▼
FastAPI on localhost:8787
        ├── SQLite  (documents, blocks, translations, notes, highlights, assistant)
        ├── data/library/{doc_id}.pdf
        └── OpenAI-compatible chat API (translation + assistant)
```

1. **Upload** a PDF → stored under `data/library/`  
2. **Parse** with PyMuPDF → ordered text blocks + bounding boxes in SQLite  
3. **Translate** block-by-block via your configured provider  
4. **Read** with pdf.js overlays (embedded) or a mirrored translation pane (side-by-side)  
5. **Annotate** with notes / highlights; **ask** the Paper Assistant with scoped context  

---

## Feature highlights

| Capability | Detail |
|------------|--------|
| Bilingual reader | Embedded + side-by-side, layout-aligned |
| Translation | OpenAI-compatible providers; per-block progress & retry |
| Paper Assistant | Context: selected block → page → full document |
| Library | Local list, status, open / delete |
| Notes & highlights | Anchored to blocks / pages |
| Typography | Font family, size, line height for translations |
| i18n UI | Chinese / English interface |
| Privacy | Localhost + on-disk data; keys stay local |
| Export | Word (.docx) bilingual export |

---

## Requirements

- **Windows** recommended for the one-click start script (`scripts/start.ps1`)  
- **Python 3.11+** (API)  
- **Node.js 18+** (Vite frontend)  
- A **text-based PDF** (born-digital). Scanned/image-only PDFs are detected and marked unsupported in this version — OCR is not included yet  
- An **OpenAI-compatible API** (or local model server) for translation and assistant  

---

## Quick start

### Recommended (Windows)

From the repository root:

```powershell
.\scripts\start.ps1
```

This starts the API and the Vite app and opens **http://127.0.0.1:5173/** .

**Closing the browser tab stops both frontend and backend** (heartbeat + shutdown beacon).

To keep servers running without a browser tab:

```powershell
$env:LT_AUTO_SHUTDOWN = "0"
.\scripts\start.ps1
```

### Manual start

**Backend**

```bash
cd apps/api
python3.11 -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

**Frontend** (second terminal)

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open http://127.0.0.1:5173/ → **Settings** → add a provider → return to **Library** → upload a PDF → **Translate** → read.

---

## First 5 minutes

1. **Add a provider** — Settings → choose a preset or custom Base URL + model + API key → Test → set as default  
2. **Upload a paper** — Library → Upload PDF (prefer a text-selectable academic PDF)  
3. **Translate** — open the reader → Translate; watch per-page / per-block progress  
4. **Pick a view** — Embedded (translation under each block) or Side-by-side  
5. **Go deeper** — select a dense paragraph → Notes or Paper Assistant → ask what the method claims  

---

## Configuration

### Translation providers

In **Settings** you can:

- Use vendor presets or a fully custom OpenAI-compatible Base URL  
- Preview the resolved chat-completions URL  
- Toggle **full URL mode** for non-standard gateways  
- Keep multiple profiles and switch the default  

API keys are stored only under local `data/` (obfuscated at rest with a machine-local key file).

### Reading preferences

- Default view mode: embedded vs side-by-side  
- Translation typography: font family, size, line height  
- UI language: 中文 / English  

### Runtime data

| Path | Contents |
|------|----------|
| `data/lit.db` | SQLite: documents, blocks, translations, notes, assistant |
| `data/library/` | Uploaded PDFs |
| `data/` key file | Local encryption material for API keys |

`data/` is gitignored. Treat it as your private library.

---

## Tech stack

| Layer | Stack |
|-------|--------|
| Frontend | Vue 3, Vite, TypeScript, pdf.js, Vue Router |
| Backend | FastAPI, SQLAlchemy, aiosqlite, PyMuPDF, httpx |
| Storage | SQLite + on-disk PDFs |
| AI | OpenAI-compatible Chat Completions (translation + paper assistant) |
| Export | python-docx |

---

## Product principles

- **Layout is meaning** — translation must respect where text lives on the page  
- **Local-first** — papers and keys stay on your machine by default  
- **Model-agnostic** — bring the endpoint that fits your budget, latency, or lab policy  
- **Reading > dumping text** — notes, highlights, and a scoped assistant support understanding, not just conversion  

---

## Current limitations

- No cloud accounts / multi-user sync  
- No OCR pipeline for scanned PDFs (unsupported with a clear status)  
- Paper Assistant is request/response (no streaming in v1); one thread per document  
- Vision / figure understanding and embedding RAG are out of scope for this version  
- Word export is best-effort structure, not a pixel-perfect replica of the PDF  

---

## Project layout

```
Literature Translator/
├── apps/
│   ├── api/          # FastAPI backend
│   └── web/          # Vue 3 frontend
├── scripts/          # start.ps1 and diagnostics
├── docs/             # design specs & plans
└── data/             # runtime DB + PDFs (local, gitignored)
```

---

## Contributing

Issues and PRs that improve parse quality, reading UX, provider compatibility, or documentation are welcome. Please keep product UI, code, and docs free of third-party product brand names that this project intentionally avoids referencing.

---

## License

Licensed under the [Apache License, Version 2.0](./LICENSE).

```
Copyright 2026 chenqicheng

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
