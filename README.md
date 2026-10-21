# PLF Viewer — Web timeline viewer for .plf files

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Interactive web viewer and AI query interface for PLF (PromptLine Format) files.

## Features

- **Drag & drop** `.plf` file upload (multiple files → tabs)
- **Timeline visualization** — color-coded track lanes (10 track types)
- **Click to inspect** — entry details, fields, raw PLF line
- **4 tabs** — Entry, Script (dialogue), Header, Raw PLF
- **Zoom control** — 20% to 300%
- **Embedded video monitor** — the video referenced in `CLIPS file:` is
  **resolved and loaded automatically** (searched server-side, streamed via
  `/api/video` with Range support); the *PLF cut* plays back (T:SH segments
  back-to-back); clicking any entry seeks the video; `Space` toggles playback;
  manual load button as fallback
- **Entry search** — `Ctrl+F`, matches highlighted on the timeline, click a
  result to jump
- **Model B integration** — QUERY / INSTRUCTION / PROPOSAL modes; applying an
  INSTRUCTION edits the PLF server-side and downloads the result
- **Multi-provider AI** — Groq, OpenAI, Together, OpenRouter, DeepSeek, xAI,
  Mistral, Anthropic (Claude) and local Ollama; configure via the **&#9881;
  settings** in the toolbar (provider + key stored in your browser) or via
  env vars / `.env`
- **PLF Generator** — the **Generate** tab browses your disk server-side,
  queues one job per selected video (sequential worker, Whisper is CPU-bound),
  writes one `.raw.plf` next to each source and auto-opens the results in
  the Timeline. A live **service banner** shows whether the pipeline service
  is up (with component chips + start command) and gates the Generate button;
  jobs can be **stopped, retried and removed** from the Jobs list.
  Requires the pipeline service:
  `cd plf-pipeline && python3 -m pipeline.server`
- **Keyboard shortcuts** — `Ctrl+O` open, `Ctrl+F` search, `Space` play/pause,
  `Esc` deselect

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
                        proposal, providers, apply, media resolve/stream,
                        generator: fs browse + job queue → pipeline service)
  static/index.html   ← Single-page frontend (Vanilla JS, Canvas timeline,
                        video monitor, multi-doc tabs, search)
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
