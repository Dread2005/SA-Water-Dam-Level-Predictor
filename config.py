"""
config.py — single source of truth for paths, URLs, constants.
Import this everywhere; never hardcode paths in scripts.
"""

from pathlib import Path

# ── Repo root ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()

# ── Data directories ───────────────────────────────────────────────────────────
DATA_RAW         = ROOT / "data" / "raw"
DAM_LEVELS_DIR   = DATA_RAW / "dam_levels"
RAINFALL_DIR     = DATA_RAW / "rainfall"
TEMPERATURE_DIR  = DATA_RAW / "temperature"
DATA_PROCESSED   = ROOT / "data" / "processed"
LOGS_DIR         = ROOT / "logs"

# Create on import — safe to call repeatedly
for _dir in [DAM_LEVELS_DIR, RAINFALL_DIR, TEMPERATURE_DIR, DATA_PROCESSED, LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ── DWS scraper ────────────────────────────────────────────────────────────────
DWS_BASE_URL = "https://www.dws.gov.za/Hydrology/Weekly/WRMSreport.aspx"

# Province codes used in the DWS dropdown.
# Verify these against the live page — they occasionally change.
DWS_PROVINCES = {
    "Limpopo":       "3",
    "Mpumalanga":    "4",
    "North West":    "5",
    "Gauteng":       "6",
    "Free State":    "7",
    "KwaZulu-Natal": "8",
    "Eastern Cape":  "9",
    "Northern Cape": "10",
    "Western Cape":  "11",
}

# ── CHIRPS rainfall ────────────────────────────────────────────────────────────
# Monthly CHIRPS GeoTIFFs — sub in {year} and {month:02d}
CHIRPS_URL_TEMPLATE = (
    "https://data.chc.ucsb.edu/products/CHIRPS-2.0/"
    "africa_monthly/tifs/chirps-v2.0.{year}.{month:02d}.tif.gz"
)
CHIRPS_START_YEAR = 2000   # go back far enough for lag features + baseline
SA_BBOX = (-35.0, 16.5, -22.0, 33.0)  # (south, west, north, east)

# ── ERA5 via CDS ───────────────────────────────────────────────────────────────
# Requires a ~/.cdsapirc file with your CDS API key.
# Register free at: https://cds.climate.copernicus.eu
ERA5_DATASET  = "reanalysis-era5-land-monthly-means"
ERA5_VARIABLE = "total_precipitation"

# ── Model settings ─────────────────────────────────────────────────────────────
FORECAST_HORIZONS = [30, 60, 90]   # days ahead — one XGBRegressor per horizon
TARGET_COL        = "storage_pct"  # column we're predicting
RANDOM_STATE      = 42
N_CV_SPLITS       = 5              # TimeSeriesSplit folds

# ── Output artefacts ───────────────────────────────────────────────────────────
MODEL_DIR   = ROOT / "models"
FIGURES_DIR = ROOT / "figures"
MODEL_DIR.mkdir(exist_ok=True)
FIGURES_DIR.mkdir(exist_ok=True)
