import io
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from plf import parse, get_entries, apply_edits
from plf.model_b import create_client, build_context, list_providers
from plf.model_b.providers import ensure_env_loaded

app = FastAPI(title="PLF Viewer")

PIPELINE_URL = os.environ.get("PLF_PIPELINE_URL", "http://127.0.0.1:8765")


@app.get("/", response_class=HTMLResponse)
def index():
    return Path(__file__).parent.joinpath("static", "index.html").read_text()


class ParseRequest(BaseModel):
    content: str


@app.post("/api/parse")
def api_parse(req: ParseRequest):
    plf = parse(req.content)
    scenes = []
    for s in plf.scenes:
        scenes.append({
            "id": s.id, "loc": s.loc, "time": s.time,
            "act": s.act, "desc": s.desc,
        })

    timeline = []
    for entry in plf.timeline:
        timeline.append({
            "i": entry.i,
            "o": entry.o,
            "track": entry.track,
            "fields": entry.fields,
            "raw": entry._raw_line,
        })

    return {
        "proj": plf.proj,
        "fps": plf.fps,
        "ar": plf.ar,
        "dur": plf.dur,
        "src": plf.src,
        "ref": plf.ref,
        "ctx": plf.ctx,
        "cast": [{"id": c.id, "nombre": c.nombre, "desc": c.desc} for c in plf.cast],
        "scenes": scenes,
        "clips": [{"id": c.id, "file": c.file, "tc": c.tc} for c in plf.clips],
        "timeline": timeline,
        "stats": {
            "total_entries": len(timeline),
            "shots": len(get_entries(plf, track="SH")),
            "actions": len(get_entries(plf, track="ACT")),
            "dialogues": len(get_entries(plf, track="DLG")),
            "tags": len(get_entries(plf, track="TAG")),
        },
    }


@app.get("/api/providers")
def api_providers():
    """Provider list for the settings UI. Reports key *presence*, never keys."""
    return {"providers": list_providers()}


class AIRequest(BaseModel):
    content: str
    query: str | None = None
    instruction: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


def _run_ai(req: AIRequest, mode: str):
    """Shared path for QUERY / INSTRUCTION / PROPOSAL."""
    ensure_env_loaded()
    plf = parse(req.content)
    text = req.query if mode != "instruction" else req.instruction
    ctx = build_context(plf, text)

    try:
        client = create_client(
            provider=req.provider, model=req.model, api_key=req.api_key
        )
        if mode == "query":
            result = client.query(text, plf_context=ctx)
            return {
                "interpreted_query": result.interpreted_query,
                "results": result.results,
                "summary": result.summary,
                "mode": "query",
            }
        if mode == "instruction":
            result = client.instruct(text, plf_context=ctx)
            return {
                "instruction": result.instruction,
                "edits": [
                    {"action": e.action, "i": e.i, "o": e.o, "track": e.track, "line": e.line}
                    for e in result.edits
                ],
                "affected": result.affected,
                "confirm": result.confirm,
                "mode": "instruction",
            }
        result = client.propose(text, plf_context=ctx)
        return {
            "proposal": result.proposal,
            "reasoning": result.reasoning,
            "structure": result.structure,
            "apply": result.apply,
            "mode": "proposal",
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    except Exception as e:
        return JSONResponse(status_code=502, content={"detail": f"{type(e).__name__}: {e}"})


@app.post("/api/query")
def api_query(req: AIRequest):
    return _run_ai(req, "query")


@app.post("/api/instruction")
def api_instruction(req: AIRequest):
    return _run_ai(req, "instruction")


@app.post("/api/proposal")
def api_proposal(req: AIRequest):
    return _run_ai(req, "proposal")


class ApplyRequest(BaseModel):
    content: str
    edits: list[dict]


@app.post("/api/apply")
def api_apply(req: ApplyRequest):
    """Apply Model B instruction edits → edited PLF text (Fase V2)."""
    try:
        result = apply_edits(req.content, req.edits)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    return {
        "plf_text": result.text,
        "applied": result.applied,
        "skipped": result.skipped,
        "warnings": result.warnings,
    }


# --------------------------------------------------------------------------
# Media auto-load: resolve the CLIPS file: names to real files on disk and
# stream them back to the browser (which cannot read arbitrary paths).
# --------------------------------------------------------------------------

_MEDIA_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "target", ".venv", "venv"}
_WALK_DEPTH = 3
_media_cache: dict[str, str | None] = {}
_media_allow: set[str] = set()


def _search_roots() -> list[Path]:
    roots: list[Path] = []
    for d in os.environ.get("PLF_MEDIA_DIRS", "").split(os.pathsep):
        if d:
            roots.append(Path(d).expanduser())
    here = Path(__file__).resolve().parent
    home = Path.home()
    roots += [
        Path.cwd(),
        here,
        *list(here.parents)[:2],
        home / "Documents",
        home / "Movies",
        home / "Downloads",
        home / "Desktop",
    ]
    seen, out = set(), []
    for r in roots:
        rp = r.expanduser()
        if rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out


def _resolve_media(name: str) -> str | None:
    """Find `name` (a bare filename from CLIPS file:) under the search roots."""
    if name in _media_cache:
        return _media_cache[name]
    base = Path(name).name  # never allow path traversal from PLF content
    if Path(base).suffix.lower() not in _MEDIA_EXTS:
        _media_cache[name] = None
        return None

    hit: str | None = None
    for root in _search_roots():
        if not root.is_dir():
            continue
        direct = root / base
        if direct.is_file():
            hit = str(direct)
            break
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= _WALK_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            if base in filenames:
                hit = str(Path(dirpath) / base)
                break
        if hit:
            break

    _media_cache[name] = hit
    return hit


class ResolveMediaRequest(BaseModel):
    files: list[str]


@app.post("/api/resolve_media")
def api_resolve_media(req: ResolveMediaRequest):
    """Map CLIPS filenames to stream URLs (null when not found on disk)."""
    media = {}
    for f in req.files[:20]:
        path = _resolve_media(f)
        if path:
            _media_allow.add(str(Path(path).resolve()))
            media[f] = f"/api/video?path={quote(path)}"
        else:
            media[f] = None
    return {"media": media}


@app.get("/api/video")
def api_video(path: str):
    """Stream an allow-listed media file (Range support comes from Starlette,
    which the HTML5 video element needs for seeking)."""
    p = Path(path).expanduser().resolve()
    if str(p) not in _media_allow or p.suffix.lower() not in _MEDIA_EXTS or not p.is_file():
        return JSONResponse(status_code=404, content={"detail": "media not allowed or not found"})
    ext = p.suffix.lower()
    media_type = {
        ".mp4": "video/mp4", ".m4v": "video/x-m4v", ".mov": "video/quicktime",
        ".webm": "video/webm", ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    }.get(ext, "application/octet-stream")
    return FileResponse(p, media_type=media_type, filename=p.name)


# --------------------------------------------------------------------------
# PLF Generator (PLAN.md Fase G): browse the disk, queue videos, run them
# through the pipeline service one at a time (CPU Whisper), write one
# .raw.plf per video.
# --------------------------------------------------------------------------

@app.get("/api/fs/list")
def api_fs_list(dir: str | None = None):
    """Server-side file browser — the generator runs locally, so real paths."""
    base = (Path(dir).expanduser() if dir else Path.home()).resolve()
    if not base.is_dir():
        return JSONResponse(status_code=400, content={"detail": f"not a directory: {base}"})
    subdirs, videos = [], []
    try:
        for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                subdirs.append(entry.name)
            elif entry.suffix.lower() in _MEDIA_EXTS:
                videos.append(entry.name)
    except PermissionError:
        return JSONResponse(status_code=403, content={"detail": f"permission denied: {base}"})
    return {
        "dir": str(base),
        "parent": str(base.parent) if base.parent != base else None,
        "subdirs": subdirs[:300],
        "videos": videos[:300],
    }


_jobs: list[dict] = []
_jobs_lock = threading.Lock()
_queue: "queue.Queue[dict]" = None  # type: ignore[assignment]
_plf_out_allow: set[str] = set()
_job_counter = 0


def _call_pipeline(video_path: str, context: dict) -> str:
    """POST to the pipeline service; returns the .raw.plf text.

    Kept as a single function so tests can stub it.
    """
    import httpx

    url = PIPELINE_URL.rstrip("/") + "/generate"
    r = httpx.post(url, json={"video_path": video_path, "context": context}, timeout=7200)
    if r.status_code != 200:
        raise RuntimeError(f"pipeline HTTP {r.status_code}: {r.text[:600]}")
    return r.text


def _worker():
    while True:
        job = _queue.get()
        try:
            if job.get("state") == "cancelled":
                continue  # stopped/removed while still waiting in the queue
            with _jobs_lock:
                job["state"] = "running"
                job["started"] = time.time()
            try:
                text = _call_pipeline(job["video"], job["context"])
                out = str(Path(job["video"]).with_suffix(".raw.plf"))
                with _jobs_lock:
                    if job.get("cancel"):
                        job["state"] = "cancelled"  # stop requested → discard
                    else:
                        Path(out).write_text(text, encoding="utf-8")
                        _plf_out_allow.add(str(Path(out).resolve()))
                        job["state"] = "done"
                        job["out"] = out
            except Exception as e:
                with _jobs_lock:
                    if job.get("cancel"):
                        job["state"] = "cancelled"
                    else:
                        job["state"] = "error"
                        job["error"] = str(e)
            finally:
                job["finished"] = time.time()
        finally:
            _queue.task_done()


def _ensure_worker():
    global _queue
    if _queue is None:
        import queue as _q

        _queue = _q.Queue()
        threading.Thread(target=_worker, daemon=True).start()


class GenerateRequest(BaseModel):
    files: list[str]
    context: dict = {}


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    """Queue one generation job per video (sequential worker)."""
    global _job_counter
    _ensure_worker()
    created = []
    for video in req.files[:50]:
        p = Path(video).expanduser()
        if not p.is_file() or p.suffix.lower() not in _MEDIA_EXTS:
            continue
        with _jobs_lock:
            _job_counter += 1
            job = {
                "id": _job_counter,
                "video": str(p),
                "name": p.name,
                "state": "queued",
                "out": None,
                "error": None,
                "context": req.context,
            }
            _jobs.append(job)
        _queue.put(job)
        created.append(job["id"])
    return {"queued": created}


@app.get("/api/generate/jobs")
def api_generate_jobs():
    with _jobs_lock:
        return {
            "jobs": [
                {k: j[k] for k in ("id", "name", "video", "state", "out", "error",
                                   "started", "finished", "cancel") if k in j}
                for j in _jobs[-50:]
            ]
        }


class JobActionRequest(BaseModel):
    action: str  # "stop" | "retry" | "remove"


@app.post("/api/generate/jobs/{job_id}/action")
def api_generate_job_action(job_id: int, req: JobActionRequest):
    """Job control: stop (cancel queued / discard running), retry, remove.

    Stopping a *running* job can't interrupt the pipeline call itself
    (Whisper is mid-video); the result is discarded when it returns.
    """
    _ensure_worker()
    requeue = None
    with _jobs_lock:
        job = next((j for j in _jobs if j["id"] == job_id), None)
        if job is None:
            return JSONResponse(status_code=404, content={"detail": f"job {job_id} not found"})
        state = job["state"]

        if req.action == "stop":
            if state == "queued":
                job["state"] = "cancelled"  # worker skips it when dequeued
            elif state == "running":
                job["cancel"] = True         # result discarded on completion
            else:
                return JSONResponse(status_code=409,
                                    content={"detail": f"job already {state}"})
        elif req.action == "retry":
            if state not in ("error", "cancelled"):
                return JSONResponse(status_code=409,
                                    content={"detail": f"cannot retry a {state} job"})
            job["state"] = "queued"
            job["error"] = None
            job.pop("cancel", None)
            job.pop("started", None)
            job.pop("finished", None)
            requeue = job
        elif req.action == "remove":
            if state == "running":
                return JSONResponse(status_code=409,
                                    content={"detail": "stop the job before removing it"})
            if state == "queued":
                job["state"] = "cancelled"  # stale queue entry gets skipped
            _jobs.remove(job)
        else:
            return JSONResponse(status_code=400, content={"detail": f"unknown action: {req.action}"})
    if requeue is not None:
        _queue.put(requeue)
    return {"ok": True}


@app.get("/api/generate/file")
def api_generate_file(path: str):
    """Read a finished .raw.plf (allow-listed: only job outputs)."""
    p = Path(path).expanduser().resolve()
    if str(p) not in _plf_out_allow or not p.is_file():
        return JSONResponse(status_code=404, content={"detail": "unknown output file"})
    return {"name": p.name, "content": p.read_text(encoding="utf-8")}


@app.get("/api/generate/service")
def api_generate_service():
    """Is the pipeline service reachable? Used for the UI banner."""
    import httpx

    try:
        r = httpx.get(PIPELINE_URL.rstrip("/") + "/status", timeout=3)
        if r.status_code == 200:
            return {"ok": True, "url": PIPELINE_URL, "status": r.json()}
        return {"ok": False, "url": PIPELINE_URL, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {
            "ok": False,
            "url": PIPELINE_URL,
            "detail": f"{type(e).__name__}: {e}. Start it with: cd plf-pipeline && python3 -m pipeline.server",
        }


app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
