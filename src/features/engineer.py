"""Leakage-safe feature creation for country-level daily rainfall observations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

LAGS = (1, 7, 14, 28, 56, 84)
FEATURE_COLUMNS = [
    *(f"lag_{lag}" for lag in LAGS),
    "rolling_mean_28", "rolling_mean_84", "weekly_sum", "lag_7_weekly_sum",
    "week_over_week_pct", "significant_rain_days", "days_since_significant_rain",
    "quarter", "wet_dry_flag", "days_into_season",
]


def load_rainfall(path: str | Path) -> pd.DataFrame:
    """Read the committed/live CHIRPS-style JSON and validate a daily series."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload.get("data"), list):
        raise ValueError("rainfall JSON must contain a 'data' list of [date, rainfall_mm] pairs")
    try:
        frame = pd.DataFrame(payload["data"], columns=["date", "rainfall_mm"])
    except ValueError as exc:
        raise ValueError("rainfall data must contain [date, rainfall_mm] pairs") from exc
    return _validate_daily_rainfall(frame)


def _validate_daily_rainfall(rainfall: pd.DataFrame) -> pd.DataFrame:
    """Return a strictly complete, finite, non-negative daily rainfall series.

    Invalid values and missing dates are rejected instead of being silently
    dropped: dropping them would make adjacent observations look like days.
    """
    required = {"date", "rainfall_mm"}
    if not required.issubset(rainfall.columns):
        raise ValueError(f"rainfall frame needs {sorted(required)}")
    frame = rainfall[["date", "rainfall_mm"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["rainfall_mm"] = pd.to_numeric(frame["rainfall_mm"], errors="coerce")
    if frame.empty:
        raise ValueError("rainfall input contains no observations")
    if frame["date"].isna().any():
        raise ValueError("rainfall dates must be valid daily dates")
    if not frame["date"].eq(frame["date"].dt.normalize()).all():
        raise ValueError("rainfall dates must not include times")
    if not np.isfinite(frame["rainfall_mm"]).all():
        raise ValueError("rainfall_mm must contain only finite values")
    if (frame["rainfall_mm"] < 0).any():
        raise ValueError("rainfall_mm cannot be negative")
    frame = frame.sort_values("date").reset_index(drop=True)
    if frame["date"].duplicated().any():
        raise ValueError("rainfall dates must be unique")
    if not frame["date"].diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
        raise ValueError("rainfall dates must form a complete daily series without gaps")
    return frame


def _days_since_event(events: Iterable[bool]) -> list[int]:
    days, out = 0, []
    for event in events:
        days = 0 if event else days + 1
        out.append(days)
    return out


def make_features(rainfall: pd.DataFrame, horizons: Iterable[int] = (30, 60, 90)) -> pd.DataFrame:
    """Make features known on each observation date and future cumulative targets.

    ``target_<h>`` is rainfall from the *next* day through h days ahead.  Features
    only use rainfall dated on or before the row date; rows whose future target is
    unavailable remain present for inference and are excluded by the trainer.
    """
    df = _validate_daily_rainfall(rainfall)
    for lag in LAGS:
        df[f"lag_{lag}"] = df["rainfall_mm"].shift(lag)
    df["rolling_mean_28"] = df["rainfall_mm"].rolling(28, min_periods=28).mean()
    df["rolling_mean_84"] = df["rainfall_mm"].rolling(84, min_periods=84).mean()
    df["weekly_sum"] = df["rainfall_mm"].rolling(7, min_periods=7).sum()
    df["lag_7_weekly_sum"] = df["weekly_sum"].shift(7)
    denominator = df["lag_7_weekly_sum"].replace(0, np.nan)
    df["week_over_week_pct"] = ((df["weekly_sum"] - df["lag_7_weekly_sum"]) / denominator * 100).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    # At t this threshold uses only rainfall observed before t. Day one has no
    # history, so its undefined threshold deliberately produces no event.
    threshold = df["rainfall_mm"].expanding(min_periods=1).quantile(0.75).shift(1)
    df["significant_rain_days"] = df["rainfall_mm"] > threshold
    df["days_since_significant_rain"] = _days_since_event(df["significant_rain_days"])
    df["quarter"] = df["date"].dt.quarter
    df["wet_dry_flag"] = df["date"].dt.month.isin([11, 12, 1, 2, 3, 4])
    season_start = np.where(df["date"].dt.month >= 10, df["date"].dt.year, df["date"].dt.year - 1)
    season_anchor = pd.to_datetime(pd.Series(season_start, index=df.index).astype(str) + "-10-01")
    df["days_into_season"] = (df["date"] - season_anchor).dt.days
    for horizon in horizons:
        if horizon <= 0:
            raise ValueError("forecast horizons must be positive")
        # At t, rolling result at t+h is sum(t+1 ... t+h), then shifted back to t.
        df[f"target_{horizon}"] = df["rainfall_mm"].rolling(horizon, min_periods=horizon).sum().shift(-horizon)
    return df


def training_frame(features: pd.DataFrame, horizon: int) -> pd.DataFrame:
    target = f"target_{horizon}"
    required = [*FEATURE_COLUMNS, target]
    missing = set(required) - set(features.columns)
    if missing:
        raise ValueError(f"missing feature columns: {sorted(missing)}")
    return features.dropna(subset=required).copy()


def build_from_json(input_path: str | Path, output_path: str | Path) -> pd.DataFrame:
    frame = make_features(load_rainfall(input_path))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return frame


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    built = build_from_json(root / "src/resources/rainfall.json", root / "data/feature_engineered/engineered_data.csv")
    print(f"Wrote {len(built)} rows to data/feature_engineered/engineered_data.csv")
