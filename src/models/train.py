"""Chronological, leakage-aware rainfall model training and inference."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from src.features.engineer import FEATURE_COLUMNS, training_frame


@dataclass(frozen=True)
class TrainingResult:
    horizon_days: int
    train_rows: int
    test_rows: int
    model_mae_mm: float
    baseline_mae_mm: float
    train_end_date: str
    test_start_date: str
    test_end_date: str


def _new_model() -> HistGradientBoostingRegressor:
    # Modest deterministic model; avoids the unavailable optional XGBoost dependency.
    return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)


def train_horizon(features: pd.DataFrame, horizon: int, holdout_fraction: float = 0.2) -> tuple[dict, TrainingResult]:
    """Fit a model using a chronological holdout separated by the forecast horizon."""
    if not 0 < holdout_fraction < 0.5:
        raise ValueError("holdout_fraction must be between 0 and 0.5")
    frame = training_frame(features, horizon).sort_values("date").reset_index(drop=True)
    if len(frame) < 150:
        raise ValueError("not enough feature-complete observations to train")
    target = f"target_{horizon}"
    split = int(len(frame) * (1 - holdout_fraction))
    # Targets in the final horizon days of train use outcomes overlapping holdout dates.
    train_end = split - horizon
    if train_end < 100 or split >= len(frame):
        raise ValueError("not enough rows after applying the horizon embargo")
    train, test = frame.iloc[:train_end], frame.iloc[split:]
    x_train, y_train = train[FEATURE_COLUMNS], train[target]
    x_test, y_test = test[FEATURE_COLUMNS], test[target]
    model = _new_model().fit(x_train, y_train)
    predicted = model.predict(x_test)
    baseline = np.full(len(test), y_train.mean())
    result = TrainingResult(horizon, len(train), len(test), float(mean_absolute_error(y_test, predicted)), float(mean_absolute_error(y_test, baseline)), str(train.date.iloc[-1].date()), str(test.date.iloc[0].date()), str(test.date.iloc[-1].date()))
    # Refit only after holdout evaluation. Inference artifact carries its feature schema.
    final_model = _new_model().fit(frame[FEATURE_COLUMNS], frame[target])
    artifact = {"model": final_model, "feature_columns": FEATURE_COLUMNS, "horizon_days": horizon, "target": target, "metrics": asdict(result), "model_type": "HistGradientBoostingRegressor"}
    return artifact, result


def train_all(features: pd.DataFrame, models_dir: str | Path, horizons: Iterable[int] = (30, 60, 90)) -> dict[int, TrainingResult]:
    out = Path(models_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for horizon in horizons:
        artifact, result = train_horizon(features, horizon)
        joblib.dump(artifact, out / f"xgboost_rainfall_{horizon}.pkl")
        results[horizon] = result
    return results


def predict_latest(features: pd.DataFrame, models_dir: str | Path, horizons: Iterable[int] = (30, 60, 90)) -> dict:
    latest = features.dropna(subset=FEATURE_COLUMNS).sort_values("date").iloc[-1]
    result = {"prediction_date": str(pd.Timestamp(latest.date).date()), "units": "mm", "metric": "country_level_cumulative_rainfall", "disclaimer": "Rainfall estimates only; not dam-level or dam-volume forecasts.", "forecasts": {}}
    for horizon in horizons:
        artifact = joblib.load(Path(models_dir) / f"xgboost_rainfall_{horizon}.pkl")
        columns = artifact["feature_columns"]
        value = float(artifact["model"].predict(pd.DataFrame([latest[columns].astype(float)], columns=columns))[0])
        result["forecasts"][f"{horizon}d"] = {"horizon_days": horizon, "predicted_cumulative_rainfall_mm": max(0.0, value), "model_type": artifact["model_type"]}
    return result
