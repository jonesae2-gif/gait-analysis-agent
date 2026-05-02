"""
orchestrator.py
---------------
Glues the three agents together and persists the prediction to memory.

This is the single entry point that the FastAPI layer calls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .planner import PlannerAgent
from .analyzer import AnalyzerAgent
from .critic import CriticAgent


def run_pipeline(
    *,
    memory_store,
    df: Optional[pd.DataFrame] = None,
    params: Optional[Dict[str, float]] = None,
    user_note: str = "",
) -> Dict[str, Any]:
    """
    End-to-end run: Planner → Analyzer → Critic → memory.

    Returns a dict suitable for direct JSON serialisation.
    """
    if df is None and params is None:
        raise ValueError("run_pipeline needs either a DataFrame or a params dict.")

    # 1. Planner ----------------------------------------------------------------
    planner = PlannerAgent()
    request = {
        "source": "csv" if df is not None else "manual",
        "columns": list(df.columns) if df is not None else [],
        "params": params or {},
        "user_note": user_note,
    }
    plan = planner.make_plan(request)

    # 2. Analyzer ---------------------------------------------------------------
    analyzer = AnalyzerAgent(
        weights_provider=memory_store.get_weights,
        threshold_provider=memory_store.get_threshold,
    )
    analyzer_result = analyzer.analyze(plan=plan, df=df, params=params)

    # 3. Critic -----------------------------------------------------------------
    critic = CriticAgent(memory_snapshot_provider=memory_store.snapshot)
    critic_result = critic.review(analyzer_result)

    # 4. Persist to memory ------------------------------------------------------
    pid = memory_store.record_prediction(
        metrics=analyzer_result["metrics"],
        contributions=analyzer_result["contributions"],
        score=analyzer_result["score"],
        label=critic_result["final_label"],
    )

    # 5. Aggregate response -----------------------------------------------------
    return {
        "prediction_id": pid,
        "plan": plan,
        "analysis": analyzer_result,
        "critique": critic_result,
        "memory": {
            "weights_used": analyzer_result["weights_used"],
            "threshold_used": analyzer_result["threshold"],
        },
    }
