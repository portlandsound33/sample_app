"""Technical assessment: measure each channel, compare against Min/Max limits.

Mirrors the shape of a definitions-driven assessment: a table of
(channel, parameter, min, max) rows is evaluated against a recording and
each row comes back In Range, Out of Range or No Limits.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

Measure = Callable[[np.ndarray, np.ndarray], float]


def _dominant_freq(t: np.ndarray, y: np.ndarray) -> float:
    if y.size < 4 or np.ptp(y) == 0:
        return 0.0
    dt = float(np.median(np.diff(t)))
    spec = np.abs(np.fft.rfft(y - y.mean()))
    freqs = np.fft.rfftfreq(y.size, dt)
    return float(freqs[int(np.argmax(spec[1:])) + 1])


def _slope(t: np.ndarray, y: np.ndarray) -> float:
    moving = np.abs(np.gradient(y, t)) > 1e-9
    if moving.sum() < 2:
        return 0.0
    return float(np.polyfit(t[moving], y[moving], 1)[0])


MEASURES: dict[str, Measure] = {
    "peak": lambda t, y: float(np.max(y)),
    "min": lambda t, y: float(np.min(y)),
    "mean": lambda t, y: float(np.mean(y)),
    "rms": lambda t, y: float(np.sqrt(np.mean(y ** 2))),
    "p2p": lambda t, y: float(np.ptp(y)),
    "frequency_hz": _dominant_freq,
    "slope_per_s": _slope,
}

# Sensible parameters per channel kind, used to build a starter definitions table.
DEFAULT_PARAMS: dict[str, tuple[str, ...]] = {
    "sine": ("frequency_hz", "rms", "peak"),
    "ramp": ("slope_per_s", "peak"),
    "pulse": ("peak", "mean"),
    "noise": ("rms", "p2p"),
    "constant": ("mean",),
}


def measure(df: pd.DataFrame, channel: str, parameter: str) -> float:
    if parameter not in MEASURES:
        raise KeyError(f"Unknown parameter '{parameter}'. Choose from {sorted(MEASURES)}")
    return MEASURES[parameter](df["time_s"].to_numpy(), df[channel].to_numpy())


def starter_definitions(df: pd.DataFrame, kinds: dict[str, str],
                        tolerance_pct: float = 10.0) -> pd.DataFrame:
    """Build definitions from a known-good run, with Min/Max at +/- tolerance.

    Values near zero get limits based on the channel's full range so that
    rounding noise doesn't fail the next run.
    """
    rows = []
    for ch, kind in kinds.items():
        span = float(np.ptp(df[ch])) or 1.0
        for p in DEFAULT_PARAMS.get(kind, ("mean",)):
            v = measure(df, ch, p)
            band = abs(v) * tolerance_pct / 100
            band = max(band, span * tolerance_pct / 100 * 0.1)
            rows.append({"channel": ch, "parameter": p,
                         "min": round(v - band, 6), "max": round(v + band, 6)})
    return pd.DataFrame(rows, columns=["channel", "parameter", "min", "max"])


def assess(df: pd.DataFrame, definitions: pd.DataFrame) -> pd.DataFrame:
    """Evaluate every definition row; never raises on a bad row."""
    out = []
    for row in definitions.to_dict("records"):
        ch, p = row.get("channel"), row.get("parameter")
        lo, hi = row.get("min"), row.get("max")
        rec = {"channel": ch, "parameter": p, "min": lo, "max": hi,
               "value": np.nan, "result": "", "note": ""}
        try:
            if ch not in df.columns:
                raise KeyError(f"channel '{ch}' not in data")
            rec["value"] = round(measure(df, ch, p), 6)
        except KeyError as exc:
            rec["result"], rec["note"] = "Error", str(exc).strip("'\"")
            out.append(rec)
            continue
        lo_ok = pd.isna(lo) or rec["value"] >= float(lo)
        hi_ok = pd.isna(hi) or rec["value"] <= float(hi)
        if pd.isna(lo) and pd.isna(hi):
            rec["result"] = "No Limits"
        else:
            rec["result"] = "In Range" if lo_ok and hi_ok else "Out of Range"
        out.append(rec)
    return pd.DataFrame(out, columns=["channel", "parameter", "min", "max",
                                      "value", "result", "note"])
