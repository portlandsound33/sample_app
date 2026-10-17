"""Lightweight anomaly scan: rolling robust z-score (median / MAD).

No scikit-learn needed, which keeps the app well inside Render's 512 MB
free-tier memory. Also flags channels that are constant idle fill.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

IDLE_FILL = {0xA5, 0x5A, 0xAA, 0x55}


def robust_z(y: pd.Series, window: int = 101) -> pd.Series:
    med = y.rolling(window, center=True, min_periods=1).median()
    mad = (y - med).abs().rolling(window, center=True, min_periods=1).median()
    scale = 1.4826 * mad.replace(0, np.nan)
    return ((y - med) / scale).fillna(0.0)


def scan(df: pd.DataFrame, channel: str, threshold: float = 6.0,
         window: int = 101) -> pd.DataFrame:
    """Return the samples whose |robust z| exceeds the threshold."""
    z = robust_z(df[channel], window)
    hits = df.loc[z.abs() > threshold, ["time_s", channel]].copy()
    hits["z"] = z[hits.index].round(2)
    return hits.reset_index(drop=True)


def constant_check(y: pd.Series) -> str | None:
    """Describe a constant channel, calling out idle-fill patterns."""
    if y.nunique() != 1:
        return None
    v = y.iloc[0]
    if float(v).is_integer() and int(v) in IDLE_FILL:
        return f"Constant at {int(v)} (0x{int(v):02X}): looks like idle fill, channel likely unpopulated"
    return f"Constant at {v:g}"
