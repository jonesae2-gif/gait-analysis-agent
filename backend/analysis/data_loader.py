"""
data_loader.py
--------------
Helpers for loading uploaded gait data into a pandas DataFrame,
regardless of whether the upload is real CSV bytes or a path to a sample.
"""

from __future__ import annotations

import io
from typing import Union

import pandas as pd


def load_csv(content: Union[bytes, str]) -> pd.DataFrame:
    """Load a CSV from raw bytes (uploaded file) or a filesystem path."""
    if isinstance(content, (bytes, bytearray)):
        return pd.read_csv(io.BytesIO(content))
    return pd.read_csv(content)
