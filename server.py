import io
import json
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from plf import parse, get_entries
from plf.model_b import create_client, build_context

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


class QueryRequest(BaseModel):
    content: str
    query: str


@app.post("/api/query")
def api_query(req: QueryRequest):
    plf = parse(req.content)
    ctx = build_context(plf, req.query)

    client = create_client()
    result = client.query(req.query, plf_context=ctx)

    return {
        "interpreted_query": result.interpreted_query,
        "results": result.results,
        "summary": result.summary,
        "mode": "query",
    }


class InstructionRequest(BaseModel):
    content: str
    instruction: str


@app.post("/api/instruction")
def api_instruction(req: InstructionRequest):
    plf = parse(req.content)
    ctx = build_context(plf, req.instruction)

    client = create_client()
    result = client.instruct(req.instruction, plf_context=ctx)

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


app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
