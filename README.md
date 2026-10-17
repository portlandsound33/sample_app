# Telemetry Bench

A small Streamlit app for practicing cloud deployment. It echoes the kind of work in
your DataSEA / TAP tools, using **synthetic data only**, so it's safe to put on a
public host:

- **Signals:** test-J-style channels (sines, a ramp, a decaying pulse, a noisy
  accelerometer, and an idle-fill word stuck at `0xA5`), plotted with Plotly.
- **Technical assessment:** Min/Max limits prefilled at ±N% from a known-good run,
  editable in-page or uploaded as CSV, with In Range / Out of Range results and
  CSV/JSON export. Flip **Degraded unit under test** in the sidebar to see failures.
- **Anomaly scan:** rolling median/MAD robust z-score; flags idle-fill channels.
- **Deployment info:** shows whether it's running on Render, the commit deployed,
  and a custom environment variable, so you can watch config changes take effect.

Domain logic lives in `bench/` with no Streamlit imports; `tests/` covers it and
drives the real app headlessly with `streamlit.testing.v1.AppTest`.

```
telemetry-bench/
├── app.py                 # Streamlit UI
├── bench/                 # signals, assessment, anomaly (pure Python)
├── tests/test_bench.py
├── requirements.txt       # pinned runtime deps (what Render installs)
├── requirements-dev.txt   # + pytest
├── .python-version        # 3.13 → Render uses latest 3.13.x
├── .streamlit/config.toml
└── render.yaml            # optional Blueprint (infrastructure as code)
```

---

## 1. Run it locally

```bash
cd telemetry-bench
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q                          # 6 tests should pass
streamlit run app.py               # opens http://localhost:8501
```

## 2. Push it to GitHub

Render deploys from a Git repo (GitHub, GitLab or Bitbucket). Create an **empty**
repo named `telemetry-bench` on GitHub (no README, so there's nothing to merge), then:

```bash
git init
git add .
git commit -m "Initial commit: Telemetry Bench"
git branch -M main
git remote add origin https://github.com/<you>/telemetry-bench.git
git push -u origin main
```

Your GitLab workflow works too: Render can connect to GitLab the same way.

## 3. Create the web service on Render

1. Sign up at <https://render.com> (signing in with GitHub is quickest; no card needed for free).
2. **New + → Web Service**, then connect your Git provider and pick `telemetry-bench`.
3. Fill in the form:

   | Field | Value |
   |---|---|
   | Name | `telemetry-bench` (becomes `telemetry-bench.onrender.com`; add a suffix if taken) |
   | Language / Runtime | Python 3 |
   | Branch | `main` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
   | Instance Type | **Free** |

4. Under **Advanced**:
   - **Health Check Path:** `/_stcore/health`
   - **Environment Variable:** `APP_GREETING` = `Hello from Render`
5. Click **Create Web Service** and watch the build log. You should see pip install
   the four packages, then Streamlit start. When the status turns **Live**, open the
   `.onrender.com` URL at the top of the page.

**Why the start command matters:** Render tells your app which port to listen on via
`$PORT`, and the app must bind to `0.0.0.0` (all interfaces), not `localhost`.
Get either wrong and the deploy times out with "no open ports detected."

## 4. Verify it

- Open the **Deployment info** tab: Host should say **Render ✅**, with your commit
  hash and `APP_GREETING` showing the value you set.
- Health endpoint: `curl https://<your-app>.onrender.com/_stcore/health` → `ok`.

## 5. Practice the deploy loop

These are the exercises worth doing; each one teaches a different part of the platform.

1. **Auto-deploy on push.** Change `__version__` in `bench/__init__.py` to `1.0.1`,
   commit and push. Render rebuilds automatically; the sidebar and the commit hash on
   the Deployment info tab update.
2. **Config without code.** In the dashboard, **Environment → edit `APP_GREETING`**
   and save. Render restarts the service; the new value appears with no commit.
3. **Break the build on purpose.** Add `notapackage==9.9` to `requirements.txt` and
   push. Read the failing build log, then revert. Render keeps serving the last good
   deploy while a new one fails.
4. **Roll back.** Under **Events**, pick an earlier deploy and choose **Rollback**.
5. **Feel the cold start.** Leave it idle for 15+ minutes, then reload: the first
   request takes a while as the free instance spins back up.
6. **Infrastructure as code.** Delete the service, then create it again from
   **New + → Blueprint** using `render.yaml`. Everything from step 3 comes from the file.
7. **Logs.** Open the **Logs** tab and upload a broken definitions CSV in the
   assessment tab to see how errors surface.

## Free-tier things to know

- **512 MB RAM, 0.1 CPU.** The app avoids scikit-learn and caches generated data to
  stay light. Keep the sample rate × duration modest.
- **Spins down after 15 minutes idle**; the first visit after that is slow.
- **Ephemeral disk:** anything written at runtime is gone after a restart or
  redeploy. The app only offers downloads, never writes to disk.
- **Python version** comes from `.python-version` (major.minor is fine there).
  A `PYTHON_VERSION` env var would need a full version like `3.13.5`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "No open ports detected" / deploy times out | Start command missing `--server.port $PORT --server.address 0.0.0.0` |
| Build fails resolving numpy/pandas | Python version mismatch; check `.python-version` |
| Page loads but spins forever | Usually a cold start; wait ~1 minute and reload |
| "Out of memory" in logs | Sample rate and duration too high for 512 MB |
