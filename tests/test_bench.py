"""Run with:  pytest -q"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from bench import anomaly, assessment, signals

APP = str(Path(__file__).resolve().parents[1] / "app.py")
KINDS = {c.name: c.kind for c in signals.CHANNELS}


@pytest.fixture
def run():
    return signals.generate(duration_s=4, rate_hz=1000, seed=7, glitches=0)


def test_generate_is_deterministic():
    a = signals.generate(seed=3)
    b = signals.generate(seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_measures(run):
    assert assessment.measure(run, "Sine_5Hz", "frequency_hz") == pytest.approx(5, abs=0.3)
    assert assessment.measure(run, "Sine_5Hz", "rms") == pytest.approx(2.5 / np.sqrt(2), rel=0.01)
    assert assessment.measure(run, "Ramp_3Vps", "slope_per_s") == pytest.approx(3, rel=0.01)
    assert assessment.measure(run, "Pulse_Decay", "peak") == pytest.approx(6.2, rel=0.01)


def test_known_good_passes_and_degraded_fails(run):
    defs = assessment.starter_definitions(run, KINDS, 10)
    assert (assessment.assess(run, defs)["result"] == "In Range").all()
    bad = run.copy()
    bad["Sine_5Hz"] *= 1.25
    res = assessment.assess(bad, defs)
    assert (res.loc[res["channel"] == "Sine_5Hz", "result"] == "Out of Range").any()


def test_bad_rows_do_not_raise(run):
    defs = pd.DataFrame([
        {"channel": "Nope", "parameter": "peak", "min": 0, "max": 1},
        {"channel": "Sine_5Hz", "parameter": "bogus", "min": 0, "max": 1},
        {"channel": "Sine_5Hz", "parameter": "peak", "min": np.nan, "max": np.nan},
    ])
    assert list(assessment.assess(run, defs)["result"]) == ["Error", "Error", "No Limits"]


def test_anomaly_finds_glitches():
    df = signals.generate(glitches=6)
    assert len(anomaly.scan(df, "Accel_Z", threshold=6)) >= 5
    assert "idle fill" in anomaly.constant_check(df["ENCR_FC2"])
    assert anomaly.constant_check(df["Sine_5Hz"]) is None


def test_app_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.toggle[0].set_value(True).run()   # degraded run
    assert not at.exception
    assert any(m.label == "Out of Range" and m.value != "0" for m in at.metric)
