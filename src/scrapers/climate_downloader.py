"""
src/scrapers/climate_downloader.py

Downloads CHIRPS monthly rainfall GeoTIFFs for Southern Africa and
clips them to the SA bounding box.  Saves outputs as compressed GeoTIFFs.

CHIRPS is static files on a public FTP/HTTP server — no auth required.

Usage:
    python -m src.scrapers.climate_downloader --start 2000 --end 2024
    python -m src.scrapers.climate_downloader --year 2024   # single year
"""

import argparse
import gzip
import logging
import shutil
import sys
from pathlib import Path

import requests
import rioxarray  # noqa: F401 — activates CRS extensions on xarray
import xarray as xr
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parents[2]))
from config import CHIRPS_START_YEAR, CHIRPS_URL_TEMPLATE, LOGS_DIR, RAINFALL_DIR, SA_BBOX

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "climate_downloader.log"),
    ],
)
log = logging.getLogger("climate_downloader")

SOUTH, WEST, NORTH, EAST = SA_BBOX


# ── Download helpers ───────────────────────────────────────────────────────────

def _download_file(url: str, dest: Path, chunk_size: int = 1 << 20) -> bool:
    """Stream-download `url` → `dest`.  Returns True on success."""
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(dest, "wb") as f, tqdm(
                desc=dest.name, total=total, unit="B", unit_scale=True, leave=False
            ) as bar:
                for chunk in r.iter_content(chunk_size):
                    f.write(chunk)
                    bar.update(len(chunk))
        return True
    except requests.HTTPError as e:
        log.warning("HTTP %s for %s", e.response.status_code, url)
    except Exception as exc:
        log.error("Download failed for %s: %s", url, exc)
    return False


def _decompress_gz(gz_path: Path) -> Path:
    """Decompress a .tif.gz → .tif in the same directory."""
    out_path = gz_path.with_suffix("")  # removes .gz
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    gz_path.unlink()  # remove the .gz to save space
    return out_path


def _clip_to_sa(tif_path: Path) -> Path:
    """
    Open a GeoTIFF, clip to SA bounding box, overwrite in place.
    Saves ~80% of file size vs the Africa-wide raster.
    """
    ds = xr.open_dataset(tif_path, engine="rasterio")
    clipped = ds.sel(
        x=slice(WEST, EAST),
        y=slice(NORTH, SOUTH),   # latitude is often descending in rasters
    )
    clipped.to_netcdf(tif_path.with_suffix(".nc"))
    tif_path.unlink()  # drop the unclipped TIF
    return tif_path.with_suffix(".nc")


# ── Main download loop ─────────────────────────────────────────────────────────

def download_chirps(start_year: int, end_year: int) -> None:
    """Download and clip CHIRPS monthly rainfall rasters for [start_year, end_year]."""
    log.info("CHIRPS download: %d–%d → %s", start_year, end_year, RAINFALL_DIR)

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            out_nc = RAINFALL_DIR / f"chirps_{year}_{month:02d}.nc"
            if out_nc.exists():
                log.debug("  Already exists: %s — skipping", out_nc.name)
                continue

            url = CHIRPS_URL_TEMPLATE.format(year=year, month=month)
            gz_path = RAINFALL_DIR / Path(url).name

            log.info("  Downloading %s", url)
            ok = _download_file(url, gz_path)
            if not ok:
                continue

            tif_path = _decompress_gz(gz_path)
            nc_path = _clip_to_sa(tif_path)
            log.info("  ✓ Saved clipped raster → %s", nc_path.name)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download CHIRPS monthly rainfall rasters")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--year", type=int, help="Download a single year")
    group.add_argument("--start", type=int, default=CHIRPS_START_YEAR, help="Start year")
    p.add_argument("--end", type=int, default=2024, help="End year (inclusive)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.year:
        download_chirps(args.year, args.year)
    else:
        download_chirps(args.start, args.end)
