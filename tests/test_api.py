import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

import api


def _artifact_tree(base: Path, prediction: object | None = None) -> None:
    for name in ("30", "60", "90"):
        path = base / "models" / f"xgboost_rainfall_{name}.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not loaded")
    for name in ("30", "60"):
        path = base / "maps" / f"forecast_{name}d.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<h1>{name}</h1>", encoding="utf-8")
    if prediction is not None:
        path = base / "data" / "processed" / "latest_predictions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prediction), encoding="utf-8")


def _prediction() -> dict:
    return {
        "prediction_date": "2026-11-06",
        "units": "mm",
        "metric": "country_level_cumulative_rainfall",
        "disclaimer": "Rainfall estimates only; not dam-level or dam-volume forecasts.",
        "forecasts": {
            f"{days}d": {
                "horizon_days": days,
                "predicted_cumulative_rainfall_mm": float(days),
                "model_type": "demo",
            }
            for days in (30, 60, 90)
        },
    }


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(api, "BASE", tmp_path)
    return TestClient(api.app)


def test_ready_artifacts_are_served_without_unpickling(monkeypatch, tmp_path):
    _artifact_tree(tmp_path, _prediction())
    client = _client(monkeypatch, tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["models"]["loaded"] is False
    assert health.json()["data"]["source_date"] == "2026-11-06"
    assert client.get("/predictions/latest").status_code == 200
    assert client.get("/forecast/30d").status_code == 200
    assert "rainfall" in client.get("/").json()["scope"].lower()


def test_missing_artifacts_are_degraded_and_maps_remain_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    health = client.get("/health")
    assert health.status_code == 503
    assert health.json()["status"] == "degraded"
    assert "predictions" in health.json()["missing_or_invalid"]
    assert client.get("/predictions/latest").status_code == 503
    assert client.get("/forecast/30d").status_code == 404


def test_malformed_predictions_return_503(monkeypatch, tmp_path):
    _artifact_tree(tmp_path)
    prediction_path = tmp_path / "data" / "processed" / "latest_predictions.json"
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    prediction_path.write_text("{ bad json", encoding="utf-8")
    client = _client(monkeypatch, tmp_path)

    health = client.get("/health")
    assert health.status_code == 503
    assert "predictions:invalid" in health.json()["missing_or_invalid"]
    response = client.get("/predictions/latest")
    assert response.status_code == 503
    assert "malformed" in response.json()["detail"].lower()


def test_pipeline_trigger_is_explicitly_not_implemented(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/trigger/pipeline").status_code == 501
