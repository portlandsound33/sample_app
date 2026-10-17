"""Synthetic telemetry channels.

Generates a small, test-J-style recording: sines, ramps, decaying pulses,
a constant idle-fill word and a noisy accelerometer with injected glitches.
Everything is deterministic for a given seed so results are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    kind: str          # sine | ramp | pulse | constant | noise
    units: str
    description: str


CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("Sine_5Hz", "sine", "V", "5 Hz, 2.5 V amplitude reference sine"),
    ChannelSpec("NoisySine_12Hz", "sine", "V", "12 Hz sine with additive noise"),
    ChannelSpec("Ramp_3Vps", "ramp", "V", "Linear ramp, 3 V/s"),
    ChannelSpec("Pulse_Decay", "pulse", "V", "Exponentially decaying pulse at t = 1.0 s"),
    ChannelSpec("Accel_Z", "noise", "g", "Vibration channel with injected glitches"),
    ChannelSpec("ENCR_FC2", "constant", "counts", "Unpopulated word held at idle fill 0xA5"),
)

SPEC_BY_NAME = {c.name: c for c in CHANNELS}


def generate(duration_s: float = 4.0, rate_hz: int = 1000, seed: int = 7,
             glitches: int = 6) -> pd.DataFrame:
    """Return a wide DataFrame: a ``time_s`` column plus one column per channel."""
    if duration_s <= 0 or rate_hz <= 0:
        raise ValueError("duration_s and rate_hz must be positive")
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration_s * rate_hz)) / rate_hz

    sine = 2.5 * np.sin(2 * np.pi * 5 * t)
    noisy = 1.2 * np.sin(2 * np.pi * 12 * t) + rng.normal(0, 0.15, t.size)
    ramp = np.clip(3.0 * (t - 0.5), 0, None)
    pulse = np.where(t >= 1.0, 6.2 * np.exp(-(t - 1.0) / 0.12), 0.0)

    accel = rng.normal(0, 0.05, t.size) + 0.02 * np.sin(2 * np.pi * 60 * t)
    if glitches:
        idx = rng.choice(np.arange(50, t.size - 50), size=glitches, replace=False)
        accel[idx] += rng.choice([-1, 1], size=glitches) * rng.uniform(0.6, 1.2, glitches)

    fill = np.full(t.size, 0xA5, dtype=float)

    return pd.DataFrame({
        "time_s": t,
        "Sine_5Hz": sine,
        "NoisySine_12Hz": noisy,
        "Ramp_3Vps": ramp,
        "Pulse_Decay": pulse,
        "Accel_Z": accel,
        "ENCR_FC2": fill,
    })


def channel_names(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c != "time_s"]
