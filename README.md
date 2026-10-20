# PLF Viewer — Web timeline viewer for .plf files

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Interactive web viewer and AI query interface for PLF (PromptLine Format) files.

## Features

- **Drag & drop** `.plf` file upload
- **Timeline visualization** — color-coded track lanes (10 track types)
- **Click to inspect** — entry details, fields, raw PLF line
- **4 tabs** — Entry, Script (dialogue), Header, Raw PLF
- **Zoom control** — 20% to 300%
- **Model B integration** — QUERY / INSTRUCTION / PROPOSAL modes
- **Multi-provider AI** — Groq, OpenAI, Together, OpenRouter, DeepSeek, xAI,
  Mistral, Anthropic (Claude) and local Ollama; configure via the **&#9881;
  settings** in the toolbar (provider + key stored in your browser) or via
  env vars / `.env`
- **Keyboard shortcuts** — `Ctrl+O` open, `Esc` deselect

## Quick start

```bash
cd plf-viewer
pip install -r requirements.txt
python server.py
# Open http://localhost:8000
```

No key is needed to open the app. For AI queries, either set a key in the
&#9881; settings dialog (stored in localStorage) or put one in the root
`.env` / environment, e.g. `GROQ_API_KEY=...` or `OPENAI_API_KEY=...`.

## Architecture

```
plf-viewer/
  server.py           ← FastAPI backend (parse, query, instruction,
                        proposal, providers endpoints)
  static/index.html   ← Single-page frontend (Vanilla JS, Canvas timeline)
  requirements.txt
```

## Screenshot

```
┌─────────────────────────────────────────────────────────┐
│ PLF Viewer          [Open] [100% ===]  24 shots · 4...  │
├──────────────────────────────────────┬──────────────────┤
│ SCENE ████████████████████████████   │ Entry | Scr | Hdr│
│ SHOT  ██ ███ ██ ████ ██ ██ ██ ███  │ T:SH — Shot      │
│ ACT   ██████      ██████    █████   │ i: 47.20         │
│ EL    ██ ██ ██ ██ ██ ██ ██ ██ ████ │ o: 60.00         │
│ DLG          ████         ████      │ shot: ELS        │
│ W            ████         ████      │ cam: sta         │
│ AMB   ████████████████████████████  │ mood: ale        │
│ MUS          █████████              │                  │
│ TAG          ████  ██               │ [Query input...] │
│ USR   ████████████████              │ [Ask] [Edit]    │
│                                     │ Response:        │
└──────────────────────────────────────┴──────────────────┘
```
