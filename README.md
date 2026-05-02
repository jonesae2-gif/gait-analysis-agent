# GaitMind — Cognitive-Learning Gait-Analysis Agent

A full-stack demo of a **biomedical AI agent** that performs **gait abnormality
detection** through **multi-step reasoning** and **cognitive learning**.

The system uses a three-agent pipeline (Planner → Analyzer → Critic) on top of
real (but simplified) biomechanics, and persists a lightweight learning memory
that adjusts feature weights and thresholds in response to user feedback.

```
┌──────────┐    ┌───────────┐    ┌────────┐    ┌─────────┐
│ Planner  │ -> │ Analyzer  │ -> │ Critic │ -> │ Memory  │
└──────────┘    └───────────┘    └────────┘    └─────────┘
                       ^                            │
                       └───── feature weights ──────┘
```

---

## 1. Quick start

### Requirements
- Python 3.10 or newer
- pip

### Install and run

```bash
cd gait-analysis-agent/backend
pip install -r requirements.txt
python main.py
```

Then open **http://127.0.0.1:8000** in your browser. The FastAPI server serves
the static frontend from `../frontend`, so there is no separate frontend build
step.

### Try it

1. Click **Use sample dataset** on the Analysis page.
2. Inspect the abnormality meter, the per-feature contribution chart, and the
   reasoning trace.
3. Click **This is correct** or one of the **Wrong** buttons. The memory panel
   on the same page will update immediately.

---

## 2. Folder structure

```
gait-analysis-agent/
├── backend/
│   ├── main.py                  # FastAPI app + static-frontend mount
│   ├── requirements.txt
│   ├── agents/
│   │   ├── planner.py           # PlannerAgent: plans the analysis
│   │   ├── analyzer.py          # AnalyzerAgent: runs the metrics + scoring
│   │   ├── critic.py            # CriticAgent: reviews and finalises
│   │   └── orchestrator.py      # Glues the three agents together
│   ├── analysis/
│   │   ├── gait_metrics.py      # Variability / SI / harmonic ratio / cadence
│   │   └── data_loader.py       # CSV ingestion helper
│   ├── memory/
│   │   ├── memory_store.py      # Cognitive-learning memory (JSON)
│   │   └── memory.json          # Created automatically on first run
│   └── data/
│       └── sample_gait.csv      # Bundled demo dataset
├── frontend/
│   ├── index.html               # Hero / overview
│   ├── analysis.html            # Upload, run, visualise, give feedback
│   ├── how-it-works.html        # Architecture + biomechanics + ethics
│   ├── css/styles.css
│   └── js/
│       ├── main.js              # Shared API helper
│       ├── analysis.js          # Analysis-page controller
│       └── charts.js            # Chart.js wrappers
├── Dockerfile
└── README.md
```

---

## 3. How the agent works

### Planner
Reads the request and emits a structured plan: which gait modules to run, in
what order, and why. The plan is data-shape aware — it only schedules a module
if the inputs needed to run it are actually present.

### Analyzer
Executes the plan. Computes:

- **Step-time variability** — coefficient of variation of step intervals
- **Robinson symmetry index** — `|L − R| / (½(L + R)) × 100`
- **Harmonic ratio** — even-vs-odd FFT power of vertical acceleration
- **Cadence** — steps per minute

Each metric is mapped to a 0..1 risk component using clinically-inspired
reference ranges, multiplied by the current per-feature weight (from memory),
and aggregated into a 0..100 abnormality score.

### Critic
Reviews the Analyzer's output. Flags:

- borderline scores (within ±5 points of the threshold)
- sparse-data warnings (fewer than 8 detected steps)
- conflicts between strong individual features and the overall label
- memory-driven hints (e.g. "this feature has been confirmed abnormal 6× in
  past feedback")

Then assembles the final user-facing explanation.

---

## 4. How cognitive learning is implemented

All learning state lives in `backend/memory/memory.json`:

```jsonc
{
  "feature_weights":     { "variability": 1.0, "symmetry": 1.0, ... },
  "thresholds":          { "abnormal_cutoff": 50.0 },
  "feature_correlations":{ "variability": { "normal": 2, "abnormal": 7 }, ... },
  "history":             [ /* last 200 predictions, each with feedback */ ],
  "stats":               { "total_feedback": ..., "agreements": ..., ... }
}
```

When you send feedback through the UI (or `POST /api/feedback`) the system
runs a small reinforcement-style update:

| Situation                                              | Effect                                               |
|--------------------------------------------------------|------------------------------------------------------|
| Agent said *abnormal*, user says *normal* (false +)    | Down-weight loud features, raise threshold           |
| Agent said *normal*, user says *abnormal* (false −)    | Up-weight elevated features, lower threshold         |
| Agreement                                              | No weight change; agreement counter ticks up         |
| Always                                                 | Per-feature, per-label correlation tally is updated  |

Updates use a learning rate of `Δ ≈ 0.10 × contribution`, weights are clamped
to `[0.1, 3.0]`, and the threshold is clamped to `[20, 95]`. This prevents any
single bad example from destabilising the system.

This is intentionally **not** a neural network. It's an interpretable
reinforcement-style update so that:

1. The full state is human-readable in `memory.json`.
2. Every change can be explained in the reasoning trace.
3. You can `POST /api/memory/reset` to start over for a new study.

---

## 5. API reference

| Method | Path                       | Purpose                                                  |
|--------|----------------------------|----------------------------------------------------------|
| GET    | `/api/health`              | Liveness probe                                           |
| GET    | `/api/sample-csv`          | Download the bundled sample dataset                      |
| POST   | `/api/analyze/csv`         | Upload a CSV → full pipeline result                      |
| POST   | `/api/analyze/manual`      | Submit manual gait parameters (JSON)                     |
| POST   | `/api/feedback`            | `{ prediction_id, user_label }` → updates memory         |
| GET    | `/api/memory`              | Full memory snapshot (weights, thresholds, history)      |
| POST   | `/api/memory/reset`        | Wipe memory back to defaults                             |

The Analyze response shape:

```jsonc
{
  "prediction_id": "ab12cd34ef",
  "plan":     { "agent": "Planner",  "steps": [...], "modules_to_run": [...] },
  "analysis": { "agent": "Analyzer", "metrics": {...}, "contributions": {...},
                "score": 42.3, "threshold": 50.0, "label": "normal", ... },
  "critique": { "agent": "Critic",   "confidence": 0.78, "notes": [...],
                "final_label": "normal", "final_explanation": "..." },
  "memory":   { "weights_used": {...}, "threshold_used": 50.0 }
}
```

---

## 6. Sample CSV format

```
time, accel_z, gyro_z, left_step_time, right_step_time
0.00, 1.027,   0.169,  0.5512,         0.5731
0.02, 1.307,   0.184,  0.5601,         0.5829
...
```

Columns are flexible — provide whichever subset you have:

- `time` + (`accel_z` | `acceleration` | `accel`) → variability, cadence, harmonic ratio
- `step_interval`                                  → variability, cadence
- `left_step_time` + `right_step_time`             → symmetry index

---

## 7. How to extend

- **Plug in a real LLM.** Replace `PlannerAgent.make_plan()` with an LLM call
  that returns the same JSON shape. The Analyzer/Critic don't care.
- **Add a new metric.** Add a function to `analysis/gait_metrics.py`, register a
  weight in `memory_store._DEFAULT_MEMORY["feature_weights"]`, and include it
  in `abnormality_score()`.
- **Persist per-user memory.** Replace the single `memory.json` with a
  per-user file (key on the request session) — `MemoryStore` already takes a
  path.
- **Replace the rule-based learning** with a logistic regression trained on the
  history. The history already stores all the inputs you'd need.

---

## 8. Limitations & ethics

GaitMind is a **teaching demo**, not a medical device. Reference ranges are
simplified. Real clinical assessments require instrumented walkways, multiple
trials, and expert interpretation. The shared `memory.json` means that in a
multi-user deployment, one user's feedback influences everyone's predictions —
production use would require per-user partitioning, access controls, and audit
logs. Feedback skewed toward one demographic will cause the weights and
threshold to drift toward that population's norms; reset memory before any
new study.

---

## 9. Docker (optional)

```bash
docker build -t gaitmind .
docker run --rm -p 8000:8000 gaitmind
```

Then open **http://localhost:8000**.
