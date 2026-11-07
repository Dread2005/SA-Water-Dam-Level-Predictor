import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.engineer import FEATURE_COLUMNS, make_features
from src.models.train import predict_latest, train_all
from src.viz.forecast_maps import matched_dams, write_forecast_map


def synthetic_rainfall(days=500):
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    return pd.DataFrame({"date": dates, "rainfall_mm": [(i % 17) / 3 + (i % 5 == 0) for i in range(days)]})


def test_future_target_is_aligned_to_next_days_only():
    frame = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=100), "rainfall_mm": range(100)})
    featured = make_features(frame, horizons=(3,))
    # Date index 84 has values 84,85,86,87: target is 85+86+87, not a trailing sum.
    assert featured.loc[84, "target_3"] == 85 + 86 + 87
    assert pd.isna(featured.loc[97, "target_3"])
    assert set(FEATURE_COLUMNS).issubset(featured.columns)


def test_significant_rain_threshold_is_causal_for_every_prefix():
    rainfall = synthetic_rainfall(days=140)
    full = make_features(rainfall, horizons=(3,))
    # Altering a future suffix must not change the significance features in a
    # retained prefix. This catches thresholds derived from the whole series.
    altered = rainfall.copy()
    altered.loc[100:, "rainfall_mm"] += 10_000
    changed = make_features(altered, horizons=(3,))
    columns = ["significant_rain_days", "days_since_significant_rain"]
    pd.testing.assert_frame_equal(full.loc[:99, columns], changed.loc[:99, columns])
    # The first row is an explicit cold start: no prior rainfall can define a threshold.
    assert not full.loc[0, "significant_rain_days"]
    assert full.loc[0, "days_since_significant_rain"] == 1


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf, -0.1])
def test_features_reject_nonfinite_or_negative_rainfall(invalid):
    rainfall = synthetic_rainfall(days=100)
    rainfall.loc[10, "rainfall_mm"] = invalid
    with pytest.raises(ValueError, match="finite|negative"):
        make_features(rainfall)


def test_features_reject_missing_daily_observation():
    rainfall = synthetic_rainfall(days=100).drop(index=50).reset_index(drop=True)
    with pytest.raises(ValueError, match="complete daily series without gaps"):
        make_features(rainfall)


def test_training_and_prediction_artifacts(tmp_path):
    features = make_features(synthetic_rainfall(), horizons=(30, 60, 90))
    results = train_all(features, tmp_path)
    assert set(results) == {30, 60, 90}
    assert results[30].train_end_date < results[30].test_start_date
    assert (tmp_path / "xgboost_rainfall_30.pkl").is_file()
    latest = predict_latest(features, tmp_path)
    assert latest["prediction_date"] == str(features.date.max().date())
    assert latest["forecasts"]["90d"]["predicted_cumulative_rainfall_mm"] >= 0


def test_map_output_uses_coordinate_join(tmp_path):
    dam_file = tmp_path / "dams.csv"
    locations_file = tmp_path / "locations.csv"
    pd.DataFrame({"Dam": ["Alpha Dam", "Total", "No Coordinates"], "This Week": [56.1, 0, 40]}).to_csv(dam_file, index=False)
    pd.DataFrame({"Name of dam": ["Alpha Dam", "Other"], "Country": ["South Africa", "South Africa"], "Decimal degree latitude": [-25.1, -26], "Decimal degree longitude": [28.2, 27]}).to_csv(locations_file, index=False)
    dams = matched_dams(dam_file, locations_file)
    assert dams.dam_name.tolist() == ["Alpha Dam"]
    forecast = {"forecasts": {"30d": {"predicted_cumulative_rainfall_mm": 42.5}}}
    path = write_forecast_map(dams, forecast, 30, tmp_path / "forecast.html")
    assert path.is_file()
    assert "Not a dam-level forecast" in path.read_text(encoding="utf-8")


def test_offline_pipeline_smoke(tmp_path, monkeypatch):
    # This test exercises the committed-data build without invoking network collectors.
    import orchestrator.run_pipeline as pipeline
    monkeypatch.setattr(pipeline, "ROOT", Path.cwd())
    # The real pipeline's outputs are intentionally conventional repository paths.
    summary = pipeline.build()
    assert summary["feature_rows"] > 100
    assert Path(summary["prediction_path"]).is_file()
    assert json.loads(Path(summary["prediction_path"]).read_text())["metric"] == "country_level_cumulative_rainfall"
