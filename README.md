# SA Water Dam Level Predictor

A South African water-data exploration project with a reproducible **country-level rainfall forecasting prototype** and dam-location visualizations.

**Scope:** The current models estimate cumulative rainfall over 30, 60 and 90 days. They do **not** forecast individual dam levels, capacity or volume. Dam markers are geographic context, not independent dam predictions. Rainfall is the CHIRPS spatial mean over a South Africa bounding rectangle, not a catchment-specific or exact national-boundary estimate.

## Quick start (Python 3.12)

```bash
python -m venv .venv
# Activate the virtual environment for your operating system.
python -m pip install -r requirements-dev.txt
python -m pytest -q
python orchestrator/run_pipeline.py offline
python -m uvicorn api:app --host 0.0.0.0 --port 10000
```

`offline` uses committed source inputs without Earth Engine or scraper access. The bundled rainfall observations end on **2026-06-30**: this produces a historical demonstration, **not a current forecast**. The API exposes source date, age and a stale flag.

## Outputs

- `data/feature_engineered/engineered_data.csv`: daily causal features and correctly aligned future rainfall targets.
- `models/xgboost_rainfall_{30,60,90}.pkl`: **scikit-learn HistGradientBoostingRegressor** bundles. Legacy filenames are retained for compatibility; these are not XGBoost estimators.
- `data/processed/latest_predictions.json`: predictions and source date.
- `maps/forecast_30d.html`, `maps/forecast_60d.html`: contextual Folium maps.

Models use chronological holdout with a forecast-horizon embargo, followed by refitting on available labelled history. Evaluation includes mean-baseline MAE. This is prototype validation, not proof of operational forecasting skill; future work should include seasonal/persistence baselines and rolling-origin evaluation.

## Live refresh

```bash
python orchestrator/run_pipeline.py daily
python orchestrator/run_pipeline.py weekly
```

Daily mode refreshes published CHIRPS observations before rebuilding; weekly mode additionally refreshes all nine DWS provincial tables. CHIRPS publication may lag today's date. Partial downloads are rejected and do not overwrite source files. DWS can block requests; the job fails visibly rather than silently publishing a partial provincial dataset.

Earth Engine uses non-interactive credentials only. In GitHub Actions configure repository secrets `EARTHENGINE_EMAIL` and `EARTHENGINE_KEY` (the complete service-account JSON), and repository variable `EARTHENGINE_PROJECT` for an Earth Engine-enabled Cloud project. The legacy project ID is the default. That service account must be authorized for the project and Earth Engine. Never commit keys. Local runs also accept a JSON `EARTHENGINE_CREDENTIALS` environment value or existing Earth Engine credentials.

## API

- `/`: scope information.
- `/health`: artifact readiness plus source freshness; 503 for missing/malformed required artifacts. HTTP 200 means artifacts are present, **not that data are current**; inspect `data.stale`. Model files are not deserialized by the API.
- `/predictions/latest`: validated JSON and freshness.
- `/forecast/30d`, `/forecast/60d`: maps.
- `POST /trigger/pipeline`: explicitly not implemented (501); run refreshes via GitHub Actions instead.

## Automation and deployment

`Test and offline build` runs on pushes and pull requests, tests the code, builds offline and uploads demo artifacts. `Weekly/Daily Pipeline` runs daily at 02:00 UTC and can be dispatched manually with `auto`, `daily`, `weekly` or `offline`. Live failures do not fall back silently to stale data. Successful live runs commit only refreshed source inputs; models/maps/predictions are downloadable Actions artifacts rather than growing Git history.

```bash
docker build -t sa-rainfall .
docker run --rm -p 10000:10000 sa-rainfall
```

The image builds demo artifacts from committed inputs and runs Uvicorn using `$PORT` (default 10000). Building an image is not an automatic live deployment; refreshed artifacts must be deployed/rebuilt separately. No hosted service is configured by this repair.

## Project layout

- `src/scrapers/`: import-safe collectors with atomic writes.
- `src/features/engineer.py`: causal daily feature and future-target alignment.
- `src/models/train.py`: training, holdout metrics and inference.
- `src/viz/forecast_maps.py`: conservative full-name coordinate matching and maps.
- `orchestrator/run_pipeline.py`: offline/daily/weekly entry point.
- `tests/`: feature, collector, orchestration and API regression coverage.
- `notebooks/`: original exploration, preserved as historical research rather than production entry points.

See [pipeline recovery notes](docs/PIPELINE_RECOVERY.md) for methodology and limitations.
