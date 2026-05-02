"""
critic.py
---------
CriticAgent: sanity-checks the Analyzer's output and produces the final
explanation that the user actually sees.

It looks for:
  * Borderline scores near the threshold (low confidence).
  * Conflicts between strong individual features and the aggregate label.
  * Sparse data warnings (e.g. very few detected steps).
  * Memory hints (which features the user has historically considered abnormal).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class CriticAgent:
    name = "Critic"

    def __init__(self, memory_snapshot_provider=None):
        self._snapshot = memory_snapshot_provider or (lambda: {})

    def review(self, analyzer_result: Dict[str, Any]) -> Dict[str, Any]:
        score = float(analyzer_result["score"])
        threshold = float(analyzer_result["threshold"])
        label = analyzer_result["label"]
        metrics = analyzer_result["metrics"]
        contributions = analyzer_result["contributions"]

        notes: List[str] = []
        adjustments: List[str] = []
        confidence = self._confidence(score, threshold)

        # 1. Borderline check.
        if abs(score - threshold) < 5:
            notes.append(
                f"Score ({score}) is within 5 points of the cutoff ({threshold}); "
                "the Analyzer's label should be treated as low-confidence."
            )

        # 2. Sparse data check.
        n_steps = int(metrics.get("n_steps_detected", 0))
        if n_steps and n_steps < 8:
            notes.append(
                f"Only {n_steps} steps detected — variability and cadence are "
                "estimated from very few cycles, so the score has wide error bars."
            )

        # 3. Strong-feature vs label conflict.
        loud_features = [f for f, c in contributions.items() if c > 0.5]
        if label == "normal" and loud_features:
            adjustments.append(
                "Even though the overall label is NORMAL, the following features "
                "are independently elevated: "
                + ", ".join(loud_features)
                + ". A clinician may want to review them."
            )
        if label == "abnormal" and not loud_features:
            adjustments.append(
                "The ABNORMAL label is driven by a combination of mild deviations "
                "rather than any single dominant feature."
            )

        # 4. Memory-driven hints.
        snap = self._snapshot() or {}
        corr = snap.get("feature_correlations", {})
        for feat, contrib in contributions.items():
            if contrib <= 0.10:
                continue
            tally = corr.get(feat, {})
            normal_n = int(tally.get("normal", 0))
            abnormal_n = int(tally.get("abnormal", 0))
            if abnormal_n + normal_n >= 3:
                if abnormal_n > 2 * max(normal_n, 1):
                    notes.append(
                        f"Memory: in past feedback, elevated `{feat}` has been "
                        f"confirmed abnormal {abnormal_n}× vs normal {normal_n}× — "
                        "this feature has earned credibility."
                    )
                elif normal_n > 2 * max(abnormal_n, 1):
                    notes.append(
                        f"Memory: in past feedback, elevated `{feat}` was usually "
                        f"considered normal ({normal_n} vs {abnormal_n}); treat "
                        "with caution."
                    )

        # 5. Final, user-facing summary.
        final = self._compose_final(
            analyzer_result["explanation"], notes, adjustments, confidence, label, score
        )

        return {
            "agent": self.name,
            "confidence": confidence,
            "notes": notes,
            "adjustments": adjustments,
            "final_label": label,
            "final_score": score,
            "final_explanation": final,
        }

    # -----------------------------------------------------------------------

    def _confidence(self, score: float, threshold: float) -> float:
        """Map distance-from-threshold to a 0..1 confidence."""
        distance = abs(score - threshold)
        # 0 points away => 0.5 confidence; 25 points => ~0.95.
        return round(min(0.99, 0.5 + 0.018 * distance), 2)

    def _compose_final(
        self,
        analyzer_explanation: str,
        notes: List[str],
        adjustments: List[str],
        confidence: float,
        label: str,
        score: float,
    ) -> str:
        parts = [analyzer_explanation.strip()]
        if adjustments:
            parts.append("Critic adjustments: " + " ".join(adjustments))
        if notes:
            parts.append("Notes: " + " ".join(notes))
        parts.append(
            f"Final assessment: {label.upper()} "
            f"(score {score}, confidence {int(confidence * 100)}%)."
        )
        return "\n\n".join(parts)
