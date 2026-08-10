# SA Water Dam Level Predictor

> 30 / 60 / 90-day XGBoost forecasts for South African rain levels in mm with dam points and current dam levels,
> visualised on an interactive Folium map.

---

## Quickstart

```bash
# 1. Clone and enter
git clone https://github.com/<you>/sa-dam-predictor.git
cd sa-dam-predictor

# 2. Virtual environment
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Install Playwright's browser (one-time)
playwright install chromium

# 5. Scrape this week's dam levels (all provinces)
python -m src.scrapers.dws_scraper

# 6. Download CHIRPS rainfall (2000-2024 — takes a while, ~4 GB)
python -m src.scrapers.climate_downloader --start 2000 --end 2024
```

---

## Repo structure

```
sa-dam-predictor/
├── config.py                   ← all paths, URLs, constants
├── data/
│   ├── raw/
│   │   ├── dam_levels/         ← DWS weekly scrapes (CSV + master parquet)
│   │   ├── rainfall/           ← CHIRPS monthly NetCDF rasters
│   │   └── temperature/        ← WorldClim / ERA5
│   └── processed/              ← merged, feature-engineered DataFrames
├── notebooks/
│   └── 01_eda.ipynb
├── src/
│   ├── scrapers/
│   │   ├── dws_scraper.py      ← Playwright scraper for DWS WRMS
│   │   └── climate_downloader.py
│   ├── features/
│   │   └── engineer.py         ← lag features, rolling windows, spatial joins
│   ├── models/
│   │   └── trainer.py          ← TimeSeriesSplit + XGBoost pipeline
│   └── viz/
│       └── map_builder.py      ← Folium interactive map
├── models/                     ← serialised joblib models (gitignored)
├── figures/                    ← saved chart outputs
├── logs/
└── requirements.txt
```

---

## Scraper calibration (important — do this first)

The DWS WRMS page is JS-rendered via ASP.NET. Before running the scraper at
scale, verify the selectors:

```bash
python -m src.scrapers.dws_scraper --province "Western Cape" --debug
```

This prints the first 5 rows and dtypes. If columns look wrong, open
`src/scrapers/dws_scraper.py` and adjust `_infer_column_map()` to match the
live column headers.

---

## Data sources

| Source | What | Access |
|--------|------|--------|
| [DWS WRMS](https://www.dws.gov.za/Hydrology/Weekly/WRMSreport.aspx) | Weekly dam storage % | Free |
| [CHIRPS](https://www.chc.ucsb.edu/data/chirps) | Monthly rainfall rasters | Free |
| [ERA5 / CDS](https://cds.climate.copernicus.eu) | Temperature, evaporation | Free (register) |
| [WorldClim](https://www.worldclim.org) | Historical temperature | Free |

---

## Roadmap

- [x] Phase 1 — Data ingestion (scraper + CHIRPS downloader)
- [x] Phase 2 — Feature engineering (lag features, spatial join to catchments)
- [x] Phase 3 — 30-day XGBoost model + baseline comparison
- [x] Phase 4 — 60/90-day models + Cape Town 2018 backtest
- [x] Phase 5 — Folium interactive map + charts
- [ ] Phase 6 —  Restful API intergration + GitHub portfolio write-up

---

## Known limitations

- Model degrades on unprecedented drought events (2018 was an outlier in the training distribution)
- DWS seldom updates metadata — dam capacity figures may lag construction changes
- CHIRPS is monthly resolution; sub-monthly rainfall patterns are not captured
