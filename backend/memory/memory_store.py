"""
memory_store.py
---------------
Lightweight cognitive-learning memory.

What we persist (memory.json):
  feature_weights      - per-feature multipliers used by the Analyzer
  thresholds           - dynamic thresholds (currently abnormality cutoff)
  feature_correlations - per-feature counts of "high" values seen for each
                         user-confirmed label ("normal"/"abnormal")
  history              - last N predictions + the user's verdict
  stats                - aggregate counters (total feedback, accuracy)

How we "learn":
  Each time the user marks a prediction as correct or incorrect, we run a
  reinforcement-style update:
    * If the user says "abnormal" was wrong (false positive), we slightly
      *down-weight* the features that contributed most to the score.
    * If the user says "normal" was wrong (false negative), we *up-weight*
      the features that were elevated but missed.
    * We also nudge the abnormality cutoff threshold based on the error.
  All weights are clamped to [0.1, 3.0] so the system can't run away.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


_DEFAULT_MEMORY: Dict[str, Any] = {
    "feature_weights": {
        "variability": 1.0,
        "symmetry":    1.0,
        "harmonic":    1.0,
        "cadence":     0.5,
    },
    "thresholds": {
        "abnormal_cutoff": 50.0,   # >= this => "abnormal"
    },
    "feature_correlations": {
        # filled in as: {feature: {"normal": count, "abnormal": count}}
    },
    "history": [],
    "stats": {
        "total_feedback": 0,
        "agreements":     0,
        "disagreements":  0,
    },
}

_LOCK = threading.Lock()
_LR_WEIGHTS = 0.10        # learning rate for feature weights
_LR_THRESHOLD = 1.5       # learning rate for threshold (in score points)
_WEIGHT_MIN, _WEIGHT_MAX = 0.1, 3.0
_HISTORY_CAP = 200


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------

class MemoryStore:
    def __init__(self, path: str):
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_MEMORY, f, indent=2)

    def load(self) -> Dict[str, Any]:
        with _LOCK:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        # Merge in any new default keys (forward compatibility).
        for k, v in _DEFAULT_MEMORY.items():
            data.setdefault(k, v if not isinstance(v, dict) else dict(v))
        return data

    def save(self, data: Dict[str, Any]) -> None:
        with _LOCK:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    # -----------------------------------------------------------------------
    # Public API used by the FastAPI layer
    # -----------------------------------------------------------------------

    def get_weights(self) -> Dict[str, float]:
        return self.load()["feature_weights"]

    def get_threshold(self) -> float:
        return float(self.load()["thresholds"]["abnormal_cutoff"])

    def record_prediction(
        self,
        metrics: Dict[str, Any],
        contributions: Dict[str, float],
        score: float,
        label: str,
    ) -> str:
        """Append a prediction to history. Returns its prediction_id."""
        data = self.load()
        pid = uuid.uuid4().hex[:10]
        entry = {
            "id": pid,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metrics": {k: metrics.get(k) for k in
                        ("variability", "symmetry", "harmonic_ratio", "cadence")},
            "contributions": contributions,
            "score": score,
            "label": label,
            "feedback": None,
        }
        data["history"].insert(0, entry)
        data["history"] = data["history"][:_HISTORY_CAP]
        self.save(data)
        return pid

    def apply_feedback(self, prediction_id: str, user_label: str) -> Dict[str, Any]:
        """
        Update memory based on user feedback.
        user_label must be "normal" or "abnormal" (the user's ground truth).
        Returns a summary dict describing what changed.
        """
        user_label = user_label.strip().lower()
        if user_label not in ("normal", "abnormal"):
            raise ValueError("user_label must be 'normal' or 'abnormal'")

        data = self.load()

        # Find the matching prediction.
        pred = next((p for p in data["history"] if p["id"] == prediction_id), None)
        if pred is None:
            raise KeyError(f"Unknown prediction_id: {prediction_id}")

        agreed = (pred["label"] == user_label)
        pred["feedback"] = {
            "user_label": user_label,
            "agreed": agreed,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # ---- Reinforcement update ----------------------------------------
        weights = data["feature_weights"]
        contributions = pred.get("contributions", {})
        changes: Dict[str, Dict[str, float]] = {}

        if not agreed:
            data["stats"]["disagreements"] += 1
            if pred["label"] == "abnormal" and user_label == "normal":
                # False positive: we over-flagged. Down-weight loud features.
                for feat, c in contributions.items():
                    if feat not in weights:
                        continue
                    delta = -_LR_WEIGHTS * c
                    new_w = max(_WEIGHT_MIN, min(_WEIGHT_MAX, weights[feat] + delta))
                    if new_w != weights[feat]:
                        changes[feat] = {"old": weights[feat], "new": round(new_w, 4),
                                         "delta": round(new_w - weights[feat], 4)}
                        weights[feat] = round(new_w, 4)
                data["thresholds"]["abnormal_cutoff"] = round(
                    min(95.0, data["thresholds"]["abnormal_cutoff"] + _LR_THRESHOLD), 2
                )
            else:
                # False negative: we under-flagged. Up-weight features that
                # were elevated (any positive contribution).
                for feat, c in contributions.items():
                    if feat not in weights or c <= 0:
                        continue
                    delta = _LR_WEIGHTS * max(c, 0.05)
                    new_w = max(_WEIGHT_MIN, min(_WEIGHT_MAX, weights[feat] + delta))
                    if new_w != weights[feat]:
                        changes[feat] = {"old": weights[feat], "new": round(new_w, 4),
                                         "delta": round(new_w - weights[feat], 4)}
                        weights[feat] = round(new_w, 4)
                data["thresholds"]["abnormal_cutoff"] = round(
                    max(20.0, data["thresholds"]["abnormal_cutoff"] - _LR_THRESHOLD), 2
                )
        else:
            data["stats"]["agreements"] += 1

        data["stats"]["total_feedback"] += 1

        # ---- Feature-correlation tally -----------------------------------
        corr = data["feature_correlations"]
        for feat, c in contributions.items():
            bucket = corr.setdefault(feat, {"normal": 0, "abnormal": 0})
            if c > 0.10:                # only count "loud" features
                bucket[user_label] = bucket.get(user_label, 0) + 1

        self.save(data)

        return {
            "prediction_id": prediction_id,
            "agreed": agreed,
            "changes": changes,
            "new_weights": weights,
            "new_threshold": data["thresholds"]["abnormal_cutoff"],
            "stats": data["stats"],
        }

    def reset(self) -> None:
        """Wipe memory back to defaults (handy for demos)."""
        self.save(json.loads(json.dumps(_DEFAULT_MEMORY)))

    def history(self, limit: int = 25) -> List[Dict[str, Any]]:
        return self.load()["history"][:limit]

    def snapshot(self) -> Dict[str, Any]:
        """Return the full memory blob (used by the /memory endpoint)."""
        return self.load()
