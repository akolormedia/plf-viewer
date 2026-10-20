import io
import json
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from plf import parse, get_entries
from plf.model_b import create_client, build_context, list_providers
from plf.model_b.providers import ensure_env_loaded

app = FastAPI(title="PLF Viewer")


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


app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
