"""
gait_metrics.py
---------------
Biomechanics algorithms for gait analysis.

Implements clinically-inspired (but simplified) measures:
  - Step-time variability (CV%)
  - Symmetry index between left/right
  - Harmonic ratio (smoothness of acceleration signal)
  - Cadence estimation
  - Composite abnormality score (0..100)

The functions accept either:
  * a pandas DataFrame loaded from CSV, OR
  * a dict of pre-computed parameters (manual entry).

All formulas are intentionally transparent so the Analyzer agent can
quote them in its reasoning trace.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Low-level numeric helpers
# ---------------------------------------------------------------------------

def _safe_cv(values: np.ndarray) -> float:
    """Coefficient of variation as a percentage. Returns 0 for empty/zero-mean."""
    if len(values) == 0:
        return 0.0
    mean = float(np.mean(values))
    if abs(mean) < 1e-9:
        return 0.0
    return float(np.std(values, ddof=1) / mean * 100.0) if len(values) > 1 else 0.0


def _detect_steps(accel: np.ndarray, time: np.ndarray, min_gap: float = 0.30) -> List[float]:
    """
    Very simple peak-detection on a vertical acceleration signal.
    Returns the time stamps (seconds) where heel-strikes are estimated.

    `min_gap` is the minimum time between detected steps (seconds), to
    suppress double-counting of a single peak.
    """
    if len(accel) < 3:
        return []
    threshold = float(np.mean(accel) + 0.5 * np.std(accel))
    steps: List[float] = []
    last_t = -math.inf
    for i in range(1, len(accel) - 1):
        if accel[i] > threshold and accel[i] > accel[i - 1] and accel[i] >= accel[i + 1]:
            t = float(time[i])
            if t - last_t >= min_gap:
                steps.append(t)
                last_t = t
    return steps


# ---------------------------------------------------------------------------
# Public metric functions
# ---------------------------------------------------------------------------

def step_time_variability(step_times: List[float]) -> float:
    """
    Coefficient of variation of step intervals (%).
    Higher = more irregular gait. Healthy adults are typically < ~3%.
    """
    if len(step_times) < 2:
        return 0.0
    intervals = np.diff(np.asarray(step_times, dtype=float))
    return _safe_cv(intervals)


def cadence(step_times: List[float]) -> float:
    """Steps per minute, estimated from the average inter-step interval."""
    if len(step_times) < 2:
        return 0.0
    intervals = np.diff(np.asarray(step_times, dtype=float))
    mean_interval = float(np.mean(intervals))
    if mean_interval <= 0:
        return 0.0
    return 60.0 / mean_interval


def symmetry_index(left: float, right: float) -> float:
    """
    Robinson symmetry index in % (0 = perfectly symmetric).
    SI = |L - R| / (0.5 * (L + R)) * 100
    """
    denom = 0.5 * (left + right)
    if denom <= 1e-9:
        return 0.0
    return abs(left - right) / denom * 100.0


def harmonic_ratio(signal: np.ndarray) -> float:
    """
    Harmonic ratio: ratio of summed even-harmonic power to summed odd-harmonic
    power in the FFT of the input signal. Higher values indicate a smoother,
    more periodic (healthier) gait pattern.
    """
    if len(signal) < 8:
        return 0.0
    sig = np.asarray(signal, dtype=float)
    sig = sig - np.mean(sig)
    spectrum = np.abs(np.fft.rfft(sig))
    if len(spectrum) < 4:
        return 0.0
    # Skip DC (index 0); evens at 2,4,6..., odds at 1,3,5...
    even_power = float(np.sum(spectrum[2::2] ** 2))
    odd_power = float(np.sum(spectrum[1::2] ** 2))
    if odd_power < 1e-9:
        return 0.0
    return even_power / odd_power


# ---------------------------------------------------------------------------
# Composite abnormality score
# ---------------------------------------------------------------------------

DEFAULT_FEATURE_WEIGHTS: Dict[str, float] = {
    "variability": 1.0,   # higher CV% => more abnormal
    "symmetry":    1.0,   # higher SI%  => more abnormal
    "harmonic":    1.0,   # lower HR    => more abnormal
    "cadence":     0.5,   # very low/high cadence => more abnormal
}

# Healthy reference ranges used to scale each feature into a 0..1 risk component.
REFERENCE_RANGES = {
    "variability_healthy_max": 3.0,    # % CV
    "variability_severe":      10.0,
    "symmetry_healthy_max":    3.0,    # %
    "symmetry_severe":         15.0,
    "harmonic_healthy_min":    2.0,
    "harmonic_severe":         0.5,
    "cadence_healthy_low":     95.0,   # steps/min
    "cadence_healthy_high":    125.0,
    "cadence_severe_delta":    35.0,
}


def _scale(value: float, healthy: float, severe: float, higher_is_worse: bool) -> float:
    """Map a metric to a 0..1 risk component using two reference points."""
    if higher_is_worse:
        if value <= healthy:
            return 0.0
        if value >= severe:
            return 1.0
        return (value - healthy) / (severe - healthy)
    else:
        if value >= healthy:
            return 0.0
        if value <= severe:
            return 1.0
        return (healthy - value) / (healthy - severe)


def _cadence_risk(cad: float) -> float:
    low, high = REFERENCE_RANGES["cadence_healthy_low"], REFERENCE_RANGES["cadence_healthy_high"]
    delta = REFERENCE_RANGES["cadence_severe_delta"]
    if cad == 0:
        return 0.0
    if low <= cad <= high:
        return 0.0
    distance = (low - cad) if cad < low else (cad - high)
    return min(1.0, distance / delta)


def abnormality_score(
    metrics: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Compute a 0..100 abnormality score from the metric dict.
    Returns (score, per_feature_contributions).
    """
    w = dict(DEFAULT_FEATURE_WEIGHTS)
    if weights:
        # Memory-driven weight overrides; only known keys are merged.
        for k, v in weights.items():
            if k in w:
                w[k] = max(0.0, float(v))

    var_risk = _scale(
        metrics.get("variability", 0.0),
        REFERENCE_RANGES["variability_healthy_max"],
        REFERENCE_RANGES["variability_severe"],
        higher_is_worse=True,
    )
    sym_risk = _scale(
        metrics.get("symmetry", 0.0),
        REFERENCE_RANGES["symmetry_healthy_max"],
        REFERENCE_RANGES["symmetry_severe"],
        higher_is_worse=True,
    )
    harm_risk = _scale(
        metrics.get("harmonic_ratio", REFERENCE_RANGES["harmonic_healthy_min"]),
        REFERENCE_RANGES["harmonic_healthy_min"],
        REFERENCE_RANGES["harmonic_severe"],
        higher_is_worse=False,
    )
    cad_risk = _cadence_risk(metrics.get("cadence", 0.0))

    contributions = {
        "variability": w["variability"] * var_risk,
        "symmetry":    w["symmetry"]    * sym_risk,
        "harmonic":    w["harmonic"]    * harm_risk,
        "cadence":     w["cadence"]     * cad_risk,
    }

    total_weight = sum(w.values()) if sum(w.values()) > 0 else 1.0
    score = sum(contributions.values()) / total_weight * 100.0
    return round(score, 2), {k: round(v, 4) for k, v in contributions.items()}


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def compute_metrics_from_dataframe(df: pd.DataFrame) -> Dict[str, object]:
    """
    Inspect the columns of `df` and compute as many metrics as possible.

    Recognised column conventions (case-insensitive):
      time, accel / acceleration / accel_z, gyro / gyro_z,
      step_interval, left_step_time, right_step_time
    """
    cols = {c.lower(): c for c in df.columns}
    metrics: Dict[str, object] = {}

    # 1) Detect or load step intervals.
    step_intervals: List[float] = []
    if "step_interval" in cols:
        step_intervals = df[cols["step_interval"]].dropna().astype(float).tolist()
        # Convert intervals into cumulative step times for cadence calculation.
        step_times = list(np.cumsum(step_intervals))
    elif "time" in cols and any(k in cols for k in ("accel", "acceleration", "accel_z")):
        accel_col = cols.get("accel") or cols.get("acceleration") or cols.get("accel_z")
        time = df[cols["time"]].astype(float).to_numpy()
        accel = df[accel_col].astype(float).to_numpy()
        step_times = _detect_steps(accel, time)
        if len(step_times) >= 2:
            step_intervals = list(np.diff(step_times))
    else:
        step_times = []

    metrics["variability"] = round(step_time_variability(step_times), 3)
    metrics["cadence"]     = round(cadence(step_times), 2)

    # 2) Symmetry (only when both left/right step times are provided).
    if "left_step_time" in cols and "right_step_time" in cols:
        l = float(df[cols["left_step_time"]].dropna().mean())
        r = float(df[cols["right_step_time"]].dropna().mean())
        metrics["symmetry"] = round(symmetry_index(l, r), 3)
        metrics["mean_left_step_time"] = round(l, 4)
        metrics["mean_right_step_time"] = round(r, 4)
    else:
        metrics["symmetry"] = 0.0

    # 3) Harmonic ratio from any vertical-acceleration column we have.
    accel_col_name = None
    for k in ("accel", "acceleration", "accel_z"):
        if k in cols:
            accel_col_name = cols[k]
            break
    if accel_col_name is not None:
        accel = df[accel_col_name].astype(float).to_numpy()
        metrics["harmonic_ratio"] = round(harmonic_ratio(accel), 3)
    else:
        metrics["harmonic_ratio"] = round(REFERENCE_RANGES["harmonic_healthy_min"], 3)

    metrics["n_steps_detected"] = len(step_times)
    metrics["step_times"] = [round(t, 3) for t in step_times]
    metrics["step_intervals"] = [round(i, 3) for i in step_intervals]

    return metrics


def compute_metrics_from_manual(params: Dict[str, float]) -> Dict[str, object]:
    """
    Build a metrics dict from manually-entered parameters.

    Expected keys (any may be omitted; defaults are healthy):
      step_time_variability, stride_length, cadence, symmetry_index, harmonic_ratio
    """
    return {
        "variability":    float(params.get("step_time_variability", 0.0)),
        "cadence":        float(params.get("cadence", 110.0)),
        "symmetry":       float(params.get("symmetry_index", 0.0)),
        "stride_length":  float(params.get("stride_length", 1.4)),
        "harmonic_ratio": float(params.get("harmonic_ratio",
                                           REFERENCE_RANGES["harmonic_healthy_min"])),
        "n_steps_detected": 0,
        "step_times": [],
        "step_intervals": [],
    }
