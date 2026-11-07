"""Read-only API for published country-level rainfall forecast artifacts.

The service intentionally does not deserialize model pickle files.  Serialized model
artifacts are only a deployment artifact here; predictions are published as validated
JSON by the offline pipeline.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="SA Rainfall Forecast API")

# Tests may monkeypatch this to point at an isolated artifact directory.
BASE = Path(__file__).resolve().parent
STALE_AFTER_DAYS = 10
MODEL_PATHS = {
    "30d": Path("models/xgboost_rainfall_30.pkl"),
    "60d": Path("models/xgboost_rainfall_60.pkl"),
    "90d": Path("models/xgboost_rainfall_90.pkl"),
}
MAP_PATHS = {
    "30d": Path("maps/forecast_30d.html"),
    "60d": Path("maps/forecast_60d.html"),
}
PREDICTIONS_PATH = Path("data/processed/latest_predictions.json")


def _artifact_paths(paths: dict[str, Path]) -> dict[str, bool]:
    return {name: (BASE / path).is_file() for name, path in paths.items()}


def _read_predictions() -> tuple[dict[str, Any] | None, str | None]:
    """Read and validate the published prediction document without loading models."""
    path = BASE / PREDICTIONS_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "Predictions artifact is missing."
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"Predictions artifact is unreadable or malformed: {exc.__class__.__name__}."

    if not isinstance(document, dict):
        return None, "Predictions artifact must be a JSON object."
    required = {"prediction_date", "units", "metric", "disclaimer", "forecasts"}
    missing = sorted(required - document.keys())
    if missing:
        return None, f"Predictions artifact is missing required fields: {', '.join(missing)}."
    if document["units"] != "mm" or document["metric"] != "country_level_cumulative_rainfall" or not isinstance(document["disclaimer"], str):
        return None, "Predictions artifact has invalid metadata."
    try:
        date.fromisoformat(document["prediction_date"])
    except (TypeError, ValueError):
        return None, "Predictions artifact has an invalid prediction_date."

    forecasts = document["forecasts"]
    if not isinstance(forecasts, dict):
        return None, "Predictions artifact forecasts must be an object."
    for horizon in (30, 60, 90):
        item = forecasts.get(f"{horizon}d")
        if not isinstance(item, dict):
            return None, f"Predictions artifact is missing the {horizon}d forecast."
        value = item.get("predicted_cumulative_rainfall_mm")
        if item.get("horizon_days") != horizon or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return None, f"Predictions artifact has an invalid {horizon}d forecast."
    return document, None


def _freshness(document: dict[str, Any]) -> dict[str, Any]:
    source_date = date.fromisoformat(document["prediction_date"])
    today = datetime.now(timezone.utc).date()
    age_days = (today - source_date).days
    return {
        "source_date": source_date.isoformat(),
        "age_days": age_days,
        "stale": age_days > STALE_AFTER_DAYS,
        "stale_after_days": STALE_AFTER_DAYS,
    }


def _health_report() -> tuple[dict[str, Any], bool]:
    models_present = _artifact_paths(MODEL_PATHS)
    maps_present = _artifact_paths(MAP_PATHS)
    predictions, predictions_error = _read_predictions()
    prediction_present = (BASE / PREDICTIONS_PATH).is_file()
    freshness = _freshness(predictions) if predictions else None

    missing: list[str] = []
    missing.extend(f"model:{name}" for name, present in models_present.items() if not present)
    missing.extend(f"map:{name}" for name, present in maps_present.items() if not present)
    if not prediction_present:
        missing.append("predictions")
    if predictions_error and prediction_present:
        missing.append("predictions:invalid")

    # Pickles are deliberately never loaded by this API, so file presence must not
    # be represented as a loaded or executable model.
    report: dict[str, Any] = {
        "status": "ok" if not missing else "degraded",
        "scope": "Country-level cumulative rainfall forecasts only; not dam-level or dam-volume forecasts.",
        "artifacts": {
            "model_files_present": models_present,
            "maps_present": maps_present,
            "predictions_file_present": prediction_present,
        },
        "models": {
            "loaded": False,
            "reason": "Serialized model files are not loaded by the API; it serves validated published prediction JSON.",
        },
        "missing_or_invalid": missing,
        "data": freshness,
    }
    if predictions_error:
        report["predictions_error"] = predictions_error
    return report, not missing


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "SA Rainfall Forecast API",
        "scope": "Country-level cumulative rainfall forecasts only; not dam-level or dam-volume forecasts.",
    }


@app.get("/health")
def health() -> JSONResponse:
    report, ready = _health_report()
    return JSONResponse(status_code=200 if ready else 503, content=report)


def _map_response(horizon: str) -> HTMLResponse:
    path = BASE / MAP_PATHS[horizon]
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{horizon}-day map not generated yet")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/forecast/30d", response_class=HTMLResponse)
def get_30d_map() -> HTMLResponse:
    return _map_response("30d")


@app.get("/forecast/60d", response_class=HTMLResponse)
def get_60d_map() -> HTMLResponse:
    return _map_response("60d")


@app.get("/predictions/latest")
def latest_predictions() -> dict[str, Any]:
    predictions, error = _read_predictions()
    if error:
        raise HTTPException(status_code=503, detail=error)
    assert predictions is not None
    response = dict(predictions)
    response["freshness"] = _freshness(predictions)
    response["scope"] = "Country-level cumulative rainfall forecasts only; not dam-level or dam-volume forecasts."
    return response


@app.post("/trigger/pipeline", status_code=501)
def trigger_pipeline() -> None:
    """Pipeline triggering is intentionally not implemented by this read-only API."""
    raise HTTPException(status_code=501, detail="Pipeline triggering is not implemented by this API.")
