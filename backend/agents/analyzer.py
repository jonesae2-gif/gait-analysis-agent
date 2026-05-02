"""
analyzer.py
-----------
AnalyzerAgent: actually runs the gait analysis modules selected by the Planner,
then writes a plain-language biomechanical explanation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from analysis.gait_metrics import (
    REFERENCE_RANGES,
    abnormality_score,
    compute_metrics_from_dataframe,
    compute_metrics_from_manual,
)


class AnalyzerAgent:
    name = "Analyzer"

    def __init__(self, weights_provider=None, threshold_provider=None):
        """
        weights_provider:   callable returning the current per-feature weights
        threshold_provider: callable returning the current abnormal cutoff
        """
        self._weights = weights_provider or (lambda: None)
        self._threshold = threshold_provider or (lambda: 50.0)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def analyze(
        self,
        plan: Dict[str, Any],
        df: Optional[pd.DataFrame] = None,
        params: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        # 1. Compute raw metrics.
        if df is not None:
            metrics = compute_metrics_from_dataframe(df)
            data_source = "csv"
        else:
            metrics = compute_metrics_from_manual(params or {})
            data_source = "manual"

        # 2. Composite abnormality score (memory-aware).
        weights = self._weights()
        score, contributions = abnormality_score(metrics, weights=weights)
        threshold = float(self._threshold())
        label = "abnormal" if score >= threshold else "normal"

        # 3. Build a concise biomechanical explanation.
        explanation = self._explain(metrics, contributions, score, threshold, label)

        # 4. Surface the reasoning trail.
        trace = [
            f"Plan called for modules: {', '.join(plan.get('modules_to_run', [])) or 'none'}.",
            f"Data source: {data_source}.",
            self._format_metric_line(metrics),
            (
                f"Per-feature contributions (weight × risk): "
                + ", ".join(f"{k}={v}" for k, v in contributions.items())
            ),
            (
                f"Composite score = {score} (threshold = {threshold}) → "
                f"label = {label.upper()}."
            ),
        ]

        return {
            "agent": self.name,
            "metrics": metrics,
            "contributions": contributions,
            "score": score,
            "threshold": threshold,
            "label": label,
            "explanation": explanation,
            "trace": trace,
            "weights_used": weights,
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _format_metric_line(self, m: Dict[str, Any]) -> str:
        return (
            f"Computed metrics: variability={m.get('variability', 0)}% CV, "
            f"symmetry={m.get('symmetry', 0)}% SI, "
            f"harmonic_ratio={m.get('harmonic_ratio', 0)}, "
            f"cadence={m.get('cadence', 0)} steps/min, "
            f"steps_detected={m.get('n_steps_detected', 0)}."
        )

    def _explain(
        self,
        metrics: Dict[str, Any],
        contributions: Dict[str, float],
        score: float,
        threshold: float,
        label: str,
    ) -> str:
        bits = []
        v = float(metrics.get("variability", 0))
        s = float(metrics.get("symmetry", 0))
        h = float(metrics.get("harmonic_ratio", 0))
        c = float(metrics.get("cadence", 0))

        if v <= REFERENCE_RANGES["variability_healthy_max"]:
            bits.append(f"Step-time variability is low ({v}% CV), suggesting a "
                        "consistent rhythm.")
        elif v >= REFERENCE_RANGES["variability_severe"]:
            bits.append(f"Step-time variability is markedly elevated ({v}% CV), a "
                        "pattern often associated with fall risk in older adults.")
        else:
            bits.append(f"Step-time variability is mildly elevated ({v}% CV); worth "
                        "watching but not yet in the clinically severe range.")

        if s <= REFERENCE_RANGES["symmetry_healthy_max"]:
            bits.append(f"Left/right symmetry is good (SI = {s}%).")
        elif s >= REFERENCE_RANGES["symmetry_severe"]:
            bits.append(f"Asymmetry is large (SI = {s}%), commonly seen with "
                        "post-stroke hemiparesis or unilateral pain.")
        else:
            bits.append(f"There is mild asymmetry (SI = {s}%), possibly compensatory.")

        if h >= REFERENCE_RANGES["harmonic_healthy_min"]:
            bits.append(f"Harmonic ratio of {h} indicates a smooth, periodic "
                        "acceleration signal.")
        elif h <= REFERENCE_RANGES["harmonic_severe"]:
            bits.append(f"Harmonic ratio is low ({h}), suggesting reduced gait "
                        "smoothness/regularity.")
        else:
            bits.append(f"Harmonic ratio of {h} is borderline.")

        if c > 0:
            if (REFERENCE_RANGES["cadence_healthy_low"]
                    <= c <= REFERENCE_RANGES["cadence_healthy_high"]):
                bits.append(f"Cadence of {c} steps/min is within the typical adult range.")
            else:
                bits.append(f"Cadence of {c} steps/min is outside the typical adult range.")

        bits.append(
            f"Weighted composite score is {score}/100 (cutoff {threshold}), so the "
            f"Analyzer's preliminary label is **{label.upper()}**."
        )
        return " ".join(bits)
