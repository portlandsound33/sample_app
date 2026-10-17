"""Telemetry Bench: a small Streamlit app for practicing cloud deployment.

Run locally:   streamlit run app.py
On Render:     streamlit run app.py --server.port $PORT --server.address 0.0.0.0
"""

from __future__ import annotations

import io
import json
import os
import platform

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bench import __version__
from bench import anomaly, assessment, signals

st.set_page_config(page_title="Telemetry Bench", page_icon="📡", layout="wide")

RESULT_COLORS = {"In Range": "#d7f5dd", "Out of Range": "#fbd5d5",
                 "No Limits": "#eeeeee", "Error": "#fde8c8"}


# ---------------------------------------------------------------- data ----
@st.cache_data(show_spinner=False)
def load_run(duration: float, rate: int, seed: int, glitches: int,
             degrade: bool) -> pd.DataFrame:
    df = signals.generate(duration, rate, seed, glitches)
    if degrade:  # simulate a drifting unit under test
        df["Sine_5Hz"] *= 1.25
        df["Ramp_3Vps"] *= 0.8
        df["Pulse_Decay"] *= 0.7
    return df


@st.cache_data(show_spinner=False)
def baseline_definitions(duration: float, rate: int, tolerance: float) -> pd.DataFrame:
    """Limits come from a fixed known-good run (seed 7, no degradation)."""
    good = signals.generate(duration, rate, seed=7, glitches=0)
    kinds = {c.name: c.kind for c in signals.CHANNELS}
    return assessment.starter_definitions(good, kinds, tolerance)


def plot_channels(df: pd.DataFrame, chans: list[str],
                  marks: pd.DataFrame | None = None) -> go.Figure:
    fig = go.Figure()
    for ch in chans:
        fig.add_trace(go.Scattergl(x=df["time_s"], y=df[ch], name=ch, mode="lines"))
    if marks is not None and not marks.empty:
        ch = chans[0]
        fig.add_trace(go.Scatter(x=marks["time_s"], y=marks[ch], name="anomaly",
                                 mode="markers",
                                 marker=dict(size=10, color="#d62728", symbol="x")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="time (s)", legend=dict(orientation="h", y=1.08))
    return fig


# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.title("📡 Telemetry Bench")
    st.caption(f"v{__version__} · synthetic data only")
    st.subheader("Recording")
    duration = st.slider("Duration (s)", 1.0, 10.0, 4.0, 0.5)
    rate = st.select_slider("Sample rate (Hz)", [250, 500, 1000, 2000], value=1000)
    seed = st.number_input("Random seed", 0, 9999, 7, step=1)
    glitches = st.slider("Injected glitches (Accel_Z)", 0, 20, 6)
    degrade = st.toggle("Degraded unit under test", value=False,
                        help="Scales a few channels to make the assessment fail.")

df = load_run(duration, int(rate), int(seed), glitches, degrade)
names = signals.channel_names(df)

tab_sig, tab_ta, tab_anom, tab_env = st.tabs(
    ["Signals", "Technical assessment", "Anomaly scan", "Deployment info"])

# ------------------------------------------------------------- signals ----
with tab_sig:
    st.subheader("Waveforms")
    picked = st.multiselect("Channels", names, default=["Sine_5Hz", "Ramp_3Vps"])
    if picked:
        st.plotly_chart(plot_channels(df, picked), width="stretch")
    else:
        st.info("Pick at least one channel.")

    st.dataframe(pd.DataFrame([{"channel": c.name, "kind": c.kind, "units": c.units,
                                "description": c.description} for c in signals.CHANNELS]),
                 hide_index=True, width="stretch")
    st.download_button("Download time/value CSV", df.to_csv(index=False),
                       "telemetry_run.csv", "text/csv")

# ---------------------------------------------------------- assessment ----
with tab_ta:
    st.subheader("Assess this run against Min/Max limits")
    left, right = st.columns([1, 2])
    with left:
        tol = st.number_input("Starter tolerance (± %)", 1.0, 50.0, 10.0, 1.0,
                              help="Limits are prefilled from a known-good run.")
        uploaded = st.file_uploader("…or upload definitions CSV",
                                    type="csv",
                                    help="Columns: channel, parameter, min, max")
        st.caption("Parameters: " + ", ".join(sorted(assessment.MEASURES)))

    if uploaded is not None:
        try:
            defs = pd.read_csv(uploaded)
            missing = {"channel", "parameter", "min", "max"} - set(defs.columns)
            if missing:
                st.error(f"Definitions CSV is missing columns: {', '.join(sorted(missing))}")
                st.stop()
        except Exception as exc:  # noqa: BLE001 - surface any parse error to the user
            st.error(f"Couldn't read that CSV: {exc}")
            st.stop()
    else:
        defs = baseline_definitions(duration, int(rate), tol)

    with right:
        defs = st.data_editor(defs, num_rows="dynamic", width="stretch",
                              key="defs_editor")

    results = assessment.assess(df, defs)
    counts = results["result"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requirements", len(results))
    c2.metric("In Range", int(counts.get("In Range", 0)))
    c3.metric("Out of Range", int(counts.get("Out of Range", 0)))
    c4.metric("Errors / No Limits",
              int(counts.get("Error", 0) + counts.get("No Limits", 0)))

    st.dataframe(
        results.style.apply(
            lambda r: [f"background-color: {RESULT_COLORS.get(r['result'], '')}"] * len(r),
            axis=1),
        hide_index=True, width="stretch")

    d1, d2, d3 = st.columns(3)
    d1.download_button("Results CSV", results.to_csv(index=False),
                       "assessment_results.csv", "text/csv")
    d2.download_button("Results JSON", results.to_json(orient="records", indent=2),
                       "assessment_results.json", "application/json")
    d3.download_button("Definitions CSV", pd.DataFrame(defs).to_csv(index=False),
                       "definitions.csv", "text/csv")

# ------------------------------------------------------------- anomaly ----
with tab_anom:
    st.subheader("Rolling robust z-score scan")
    a1, a2, a3 = st.columns(3)
    ch = a1.selectbox("Channel", names, index=names.index("Accel_Z"))
    thr = a2.slider("Threshold |z|", 3.0, 15.0, 6.0, 0.5)
    win = a3.slider("Window (samples)", 21, 501, 101, 20)

    note = anomaly.constant_check(df[ch])
    if note:
        st.warning(note)
        hits = pd.DataFrame(columns=["time_s", ch, "z"])
    else:
        hits = anomaly.scan(df, ch, thr, win)
        st.metric("Samples flagged", len(hits))
    st.plotly_chart(plot_channels(df, [ch], hits), width="stretch")
    if not hits.empty:
        st.dataframe(hits, hide_index=True, width="stretch")

# ---------------------------------------------------------- environment ----
with tab_env:
    st.subheader("Where is this running?")
    on_render = os.environ.get("RENDER") == "true"
    st.write("**Host:** " + ("Render ✅" if on_render else "local machine"))
    info = {
        "app_version": __version__,
        "python": platform.python_version(),
        "streamlit": st.__version__,
        "render_service": os.environ.get("RENDER_SERVICE_NAME", "-"),
        "render_git_commit": os.environ.get("RENDER_GIT_COMMIT", "-")[:7],
        "external_url": os.environ.get("RENDER_EXTERNAL_URL", "-"),
        "port": os.environ.get("PORT", "8501 (default)"),
        "greeting_env_var": os.environ.get("APP_GREETING", "(not set)"),
    }
    st.json(info)
    st.caption("APP_GREETING is a custom environment variable: set it in the Render "
               "dashboard (Environment tab) to practice config without code changes.")
    buf = io.StringIO()
    json.dump(info, buf, indent=2)
    st.download_button("Download diagnostics", buf.getvalue(), "diagnostics.json")
