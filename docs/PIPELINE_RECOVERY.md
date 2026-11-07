# Pipeline recovery notes

## What is being forecast

The historical source is a single daily, country-level rainfall series in `src/resources/rainfall.json`. The models estimate its **next 30, 60, or 90 days of cumulative rainfall (mm)**. They do **not** estimate individual dam levels, dam storage, inflow, or water availability. Dam markers on the 30/60-day maps provide geographic context only and repeat the country-level rainfall estimate.

## Repaired execution path

```bash
python orchestrator/run_pipeline.py offline
```

Offline mode rebuilds, from committed inputs only:

- `data/feature_engineered/engineered_data.csv`
- `models/xgboost_rainfall_30.pkl`, `..._60.pkl`, `..._90.pkl`
- `data/processed/latest_predictions.json`
- `maps/forecast_30d.html`, `maps/forecast_60d.html`

Model filenames are retained for API compatibility. Their payload is a versioned-style dictionary containing a deterministic scikit-learn `HistGradientBoostingRegressor`, its exact feature schema, target/horizon, and chronological-holdout metrics; it is not an XGBoost estimator. The previous notebooks used XGBoost but XGBoost is optional/unavailable in this recovery environment.

## Method safeguards

Inputs must be a complete regular daily series: dates are valid, unique, date-only, and exactly one day apart; rainfall values must be finite and non-negative. The loader deliberately fails on gaps, duplicates, invalid dates, infinities, and negatives rather than dropping rows and allowing observations either side of a gap to masquerade as consecutive days. Every target at date *t* is the sum from *t+1* through *t+h*, rather than an accidentally trailing total. The significant-rain threshold at *t* is the expanding 75th percentile of observations strictly before *t*; the first row is an explicit no-event cold start because it has no prior history. Training removes rows with incomplete history/future targets, uses the final 20% chronologically as its holdout, and applies a horizon-length embargo before it. Evaluation occurs before the final refit on all labelled rows. No target, future target, or target-derived column is included in the feature schema.

The currently committed source covers **2000-01-01 through 2026-06-30**; generated prediction metadata uses the final source date, not the wall-clock date. Coordinate joins normalize full dam names and retain only exact normalized matches to the South African dam-coordinate resource. Unmatched dams are deliberately omitted rather than guessed from a first word. Map popup/header text is HTML-escaped before rendering and labels forecasts as country-level rainfall estimates, never dam-level forecasts.

## Live refresh

```bash
python orchestrator/run_pipeline.py daily
python orchestrator/run_pipeline.py weekly
```

These modes invoke the existing collectors and then the same build. They fail early with a clear message if non-interactive Earth Engine credentials are absent; `offline` never authenticates or uses the network. The legacy collector itself remains outside this repair scope, so deployment must supply working Earth Engine credentials/configuration.

## Validation

```bash
pytest -q
```

The focused tests cover forward-target alignment, chronological dates and persisted model artifacts, conservative coordinate joining/map content, and the offline pipeline smoke path. Folium is required for map-generation tests and full pipeline execution.
