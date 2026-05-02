"""
planner.py
----------
PlannerAgent: decides WHAT to compute and WHY.

This is a deterministic, rule-based "LLM-like" planner. The orchestrator
treats its output as a structured plan that downstream agents must follow.
Swapping in a real LLM later only requires changing `make_plan()` to call an
LLM and parse the response into the same dict shape.
"""

from __future__ import annotations

from typing import Any, Dict, List


class PlannerAgent:
    name = "Planner"

    def make_plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build an analysis plan from the incoming request.

        request keys (any may be absent):
          source: "csv" | "manual"
          columns: list of CSV column names (when source=="csv")
          params:  dict of manual gait parameters (when source=="manual")
          user_note: optional free text
        """
        source = request.get("source", "manual")
        columns = [c.lower() for c in request.get("columns", [])]
        params = request.get("params", {}) or {}

        steps: List[Dict[str, str]] = []
        modules: List[str] = []

        # Step 1 — always: ingest data and identify available signals.
        steps.append({
            "id": "1",
            "title": "Inspect input",
            "detail": (
                f"Source = {source}. "
                + (f"Columns detected: {', '.join(columns)}." if columns else
                   f"Manual parameters: {', '.join(params.keys()) or 'none'}.")
            ),
        })

        # Step 2 — choose what we can actually compute.
        if source == "csv":
            if "step_interval" in columns:
                steps.append({"id": "2a", "title": "Compute variability + cadence",
                              "detail": "Use the step_interval column directly."})
                modules.append("variability")
                modules.append("cadence")
            elif "time" in columns and any(c in columns for c in
                                           ("accel", "acceleration", "accel_z")):
                steps.append({"id": "2a", "title": "Detect heel-strikes",
                              "detail": "Run peak detection on vertical acceleration "
                                        "to estimate step times, then compute "
                                        "variability + cadence."})
                modules.extend(["variability", "cadence", "harmonic_ratio"])
            else:
                steps.append({"id": "2a", "title": "Limited temporal data",
                              "detail": "No time/accel columns found — variability "
                                        "and cadence will be unavailable."})

            if "left_step_time" in columns and "right_step_time" in columns:
                steps.append({"id": "2b", "title": "Compute symmetry index",
                              "detail": "Robinson SI from left vs right mean step time."})
                modules.append("symmetry")
        else:
            steps.append({"id": "2", "title": "Use manual parameters",
                          "detail": "Skip signal processing; build metrics straight from inputs."})
            modules.extend([k for k in
                            ("variability", "symmetry", "cadence", "harmonic_ratio")
                            if k in {
                                "variability":   "step_time_variability" in params,
                                "symmetry":      "symmetry_index"        in params,
                                "cadence":       "cadence"               in params,
                                "harmonic_ratio":"harmonic_ratio"        in params,
                            } and {
                                "variability":   "step_time_variability" in params,
                                "symmetry":      "symmetry_index"        in params,
                                "cadence":       "cadence"               in params,
                                "harmonic_ratio":"harmonic_ratio"        in params,
                            }[k]])

        # Step 3 — composite scoring.
        steps.append({"id": "3", "title": "Score abnormality",
                      "detail": "Blend per-feature risks with memory-driven weights "
                                "into a 0–100 score, then compare to the dynamic "
                                "abnormality threshold."})
        modules.append("abnormality_score")

        # Step 4 — explanation.
        steps.append({"id": "4", "title": "Hand off to Analyzer",
                      "detail": "Analyzer will compute the metrics above, generate a "
                                "biomechanical explanation, and send results to the Critic."})

        return {
            "agent": self.name,
            "steps": steps,
            "modules_to_run": list(dict.fromkeys(modules)),  # dedupe, preserve order
            "rationale": (
                "Plan is built from the data shape: we only schedule modules whose "
                "inputs are actually available, and we always finish with a composite "
                "score so the Critic has something concrete to evaluate."
            ),
        }
