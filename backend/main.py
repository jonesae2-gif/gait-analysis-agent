"""
main.py
-------
FastAPI server for the Cognitive-Learning Gait-Analysis Agent.

Endpoints
---------
GET  /api/health              quick liveness check
GET  /api/sample-csv          download the bundled sample dataset
POST /api/analyze/csv         upload a CSV and run the full agent pipeline
POST /api/analyze/manual      submit manual gait parameters
POST /api/feedback            mark a prediction correct/incorrect → updates memory
GET  /api/memory              full memory snapshot (weights, thresholds, history)
POST /api/memory/reset        wipe memory back to defaults

The server also serves the static frontend from ../frontend.
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import run_pipeline
from analysis.data_loader import load_csv
from memory.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_PATH = os.path.join(BASE_DIR, "memory", "memory.json")
SAMPLE_CSV_PATH = os.path.join(BASE_DIR, "data", "sample_gait.csv")
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

memory = MemoryStore(MEMORY_PATH)

app = FastAPI(
    title="Cognitive-Learning Gait-Analysis Agent",
    version="1.0.0",
    description=(
        "Multi-agent biomedical AI demo. Planner → Analyzer → Critic, with a "
        "lightweight cognitive-learning memory that updates on user feedback."
    ),
)

# Permissive CORS so the static frontend served from any port can talk to /api.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ManualParams(BaseModel):
    step_time_variability: Optional[float] = Field(
        None, description="Step-time CV in %, e.g. 2.3")
    stride_length: Optional[float] = Field(
        None, description="Average stride length in metres.")
    cadence: Optional[float] = Field(
        None, description="Steps per minute.")
    symmetry_index: Optional[float] = Field(
        None, description="Robinson symmetry index (%).")
    harmonic_ratio: Optional[float] = Field(
        None, description="Harmonic ratio (unitless).")
    user_note: Optional[str] = Field("", description="Free-text note for the planner.")


class FeedbackRequest(BaseModel):
    prediction_id: str
    user_label: str = Field(..., description="'normal' or 'abnormal'")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _serialise(obj: Any) -> Any:
    """Convert numpy scalars/arrays so FastAPI's default encoder is happy."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "memory_path": MEMORY_PATH}


@app.get("/api/sample-csv")
def sample_csv():
    if not os.path.exists(SAMPLE_CSV_PATH):
        raise HTTPException(status_code=404, detail="sample CSV not found")
    return FileResponse(SAMPLE_CSV_PATH, media_type="text/csv",
                        filename="sample_gait.csv")


@app.post("/api/analyze/csv")
async def analyze_csv(file: UploadFile = File(...), user_note: str = ""):
    if not file.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(status_code=400,
                            detail="Please upload a CSV (.csv) file.")
    raw = await file.read()
    try:
        df = load_csv(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}") from e

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded CSV is empty.")

    result = run_pipeline(memory_store=memory, df=df, user_note=user_note)
    return JSONResponse(_serialise(result))


@app.post("/api/analyze/manual")
def analyze_manual(payload: ManualParams):
    params = payload.dict(exclude_unset=False)
    user_note = params.pop("user_note", "") or ""
    # Drop None values so the analyzer falls back to defaults gracefully.
    params = {k: v for k, v in params.items() if v is not None}
    result = run_pipeline(memory_store=memory, params=params, user_note=user_note)
    return JSONResponse(_serialise(result))


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    try:
        update = memory.apply_feedback(req.prediction_id, req.user_label)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _serialise(update)


@app.get("/api/memory")
def memory_snapshot():
    return _serialise(memory.snapshot())


@app.post("/api/memory/reset")
def memory_reset():
    memory.reset()
    return {"status": "reset", "memory": _serialise(memory.snapshot())}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ---------------------------------------------------------------------------
# Entry-point for `python main.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
