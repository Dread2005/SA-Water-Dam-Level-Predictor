from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import json
import pandas as pd
from pathlib import Path
import joblib

app = FastAPI(title="SA Water & Rainfall Intelligence API")

BASE = Path(__file__).parent

# Load models once at startup
model_30 = joblib.load(BASE / "models" / "xgboost_rainfall_30.pkl")
model_60 = joblib.load(BASE / "models" / "xgboost_rainfall_60.pkl")
model_90 = joblib.load(BASE / "models" / "xgboost_rainfall_90.pkl")

@app.get("/")
def root():
    return {"message": "SA Water & Rainfall Intelligence API is live"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "models_loaded": all([model_30, model_60, model_90]),
    }

@app.get("/forecast/30d", response_class=HTMLResponse)
def get_30d_map():
    path = BASE / "maps" / "forecast_30d.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="30‑day map not generated yet")
    return path.read_text(encoding="utf-8")

@app.get("/forecast/60d", response_class=HTMLResponse)
def get_60d_map():
    path = BASE / "maps" / "forecast_60d.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="60‑day map not generated yet")
    return path.read_text(encoding="utf-8")

@app.get("/predictions/latest")
def latest_predictions():
    """
    Returns the most recent predicted rainfall values (mm) for the three horizons.
    Assumes your feature engineering / model inference step writes a small JSON
    or CSV with the latest predictions – adjust the path/format as needed.
    """
    pred_path = BASE / "data" / "processed" / "latest_predictions.json"
    if not pred_path.is_file():
        raise HTTPException(status_code=404, detail="Predictions file not found")
    return json.loads(pred_path.read_text())

# Optional: protected endpoint to manually retrigger the pipeline
# (use a simple token stored as an environment variable on the host)
from fastapi import Header, Status
API_TRIGGER_TOKEN = "CHANGE_ME_TO_A_SECRET"

@app.post("/trigger/pipeline", status_code=Status.HTTP_202_ACCEPTED)
def trigger_pipeline(authorization: str = Header(None)):
    if authorization != f"Bearer {API_TRIGGER_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    # In a real deployment you could call the GitHub API to create a workflow_dispatch
    # or simply return 202 and rely on the scheduled cron to pick it up soon.
    return {"msg": "Pipeline trigger accepted – next scheduled run will start shortly"}
