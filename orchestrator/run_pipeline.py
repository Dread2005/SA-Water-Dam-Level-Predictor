#!/usr/bin/env python
"""Reproducible rainfall pipeline.

``offline`` rebuilds everything from committed inputs without network access.
``daily``/``weekly`` first execute the existing live collectors, then rebuild;
they fail rather than opening an interactive credential prompt when Earth Engine
credentials are absent.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Running this file directly puts ``orchestrator/`` on sys.path, not the repo.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_live(run_type: str) -> None:
    """Run collectors only when one supported non-interactive EE auth route exists."""
    credentials = Path.home() / ".config" / "earthengine" / "credentials"
    service_account = bool(os.environ.get("EARTHENGINE_EMAIL") and os.environ.get("EARTHENGINE_KEY"))
    json_service_account = bool(os.environ.get("EARTHENGINE_CREDENTIALS"))
    if not credentials.is_file() and not service_account and not json_service_account:
        raise RuntimeError(
            "Live refresh requires non-interactive Earth Engine credentials: set "
            "EARTHENGINE_EMAIL with EARTHENGINE_KEY, EARTHENGINE_CREDENTIALS, "
            "or configure a local EE credential cache. Run `python orchestrator/run_pipeline.py offline` "
            "to use committed inputs."
        )
    commands = [[sys.executable, "src/scrapers/climate_downloader.py"]]
    if run_type == "weekly":
        commands.append([sys.executable, "src/scrapers/dws_scraper.py"])
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)


def build() -> dict:
    from src.features.engineer import build_from_json
    from src.models.train import predict_latest, train_all
    from src.viz.forecast_maps import matched_dams, write_forecast_map

    features = build_from_json(ROOT / "src/resources/rainfall.json", ROOT / "data/feature_engineered/engineered_data.csv")
    metrics = train_all(features, ROOT / "models")
    predictions = predict_latest(features, ROOT / "models")
    prediction_path = ROOT / "data/processed/latest_predictions.json"
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    prediction_path.write_text(json.dumps(predictions, indent=2), encoding="utf-8")
    dams = matched_dams(ROOT / "src/resources/all_dams_weekly.csv", ROOT / "src/resources/african_dams-African Dams.csv")
    for horizon in (30, 60):
        write_forecast_map(dams, predictions, horizon, ROOT / "maps" / f"forecast_{horizon}d.html")
    return {"feature_rows": len(features), "mapped_dams": len(dams), "metrics": {str(k): vars(v) for k, v in metrics.items()}, "prediction_path": str(prediction_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build country-level rainfall models and visualizations.")
    parser.add_argument("run_type", choices=("offline", "daily", "weekly"), help="offline uses committed data; daily/weekly refresh live inputs first")
    args = parser.parse_args(argv)
    if args.run_type != "offline":
        run_live(args.run_type)
    summary = build()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
