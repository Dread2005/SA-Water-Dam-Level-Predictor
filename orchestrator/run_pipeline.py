#!/usr/bin/env python
"""
Orchestrator for the SA‑Water‑Rainfall pipeline.
Calls existing scrapers, notebooks, and scripts in the strict sequence:
  scraper → EDA → feature engineering → Folium map generation

Usage:
    python orchestrator/run_pipeline.py <RUN_TYPE>
where RUN_TYPE is either "daily" or "weekly".
"""

import sys
import subprocess
from pathlib import Path

def run_cmd(cmd: list[str], desc: str):
    """Run a command, print its stdout/stderr, and raise on failure."""
    print(f"\n=== {desc} ===")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{desc} failed with exit code {result.returncode}")
    return result

def main(run_type: str):
    repo_root = Path(__file__).resolve().parents[1]

   
    if run_type == "daily":
        # Daily rainfall scraper only
        run_cmd(
            [sys.executable, "src/scrapers/climate_downloader.py"],
            "Running daily rainfall scraper (Weather SA)"
        )
        # NOTE: The weekly dam scraper is *not* run on daily runs
    elif run_type == "weekly":
        # Weekly dam scraper *plus* the daily rainfall scraper
        # (you said strict sequence: daily → weekly → …, so we run both)
        run_cmd(
            [sys.executable, "src/scrapers/climate_downloader.py"],
            "Running daily rainfall scraper (Weather SA)"
        )
        run_cmd(
            [sys.executable, "src/scrapers/dws_scraper.py"],
            "Running weekly dam scraper (DWS)"
        )
    else:
        raise ValueError(f"Unknown RUN_TYPE: {run_type!r}")

    # We use nbconvert to execute the notebook and write the outputs
    # to the same locations your notebook expects.
    run_cmd(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "notebook",
            "--execute",
            "--output", "01_eda_and_features_executed.ipynb",
            "--ExecutePreprocessor.timeout=600",
            "notebooks/01_eda_and_features.ipynb"
        ],
        "Executing EDA notebook (01_eda_and_features.ipynb)"
    )
    # Optionally rename the executed notebook back to the original name
    # if downstream steps rely on the exact filename.
    (repo_root / "notebooks" / "01_eda_and_features.ipynb").write_text(
        (repo_root / "01_eda_and_features_executed.ipynb").read_text()
    )
    (repo_root / "01_eda_and_features_executed.ipynb").unlink(missing_ok=True)


    # Adjust the path/module name to match your actual entry‑point.
    run_cmd(
        [sys.executable, "-m", "src.features.engineer"],
        "Running feature‑engineering script"
    )


    # You already have code that creates the maps; we expose it via a
    # small helper script or call the notebook directly.
    # Example using the existing notebook (adjust as needed):
    run_cmd(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "html",
            "--output", "maps/forecast_30d.html",
            "--ExecutePreprocessor.timeout=600",
            "notebooks/folium_map.ipynb"   # <-- your map notebook
        ],
        "Generating 30‑day Folium map"
    )
    run_cmd(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "html",
            "--output", "maps/forecast_60d.html",
            "--ExecutePreprocessor.timeout=600",
            "notebooks/folium_map_60.ipynb"   # if you have a separate 60‑day notebook
            # If you use the same notebook with a parameter, you could pass
            # an environment variable or modify the notebook call accordingly.
        ],
        "Generating 60‑day Folium map"
    )

    print("\n Pipeline completed successfully for", run_type, "run")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python orchestrator/run_pipeline.py <daily|weekly>")
        sys.exit(1)
    main(sys.argv[1].lower())
