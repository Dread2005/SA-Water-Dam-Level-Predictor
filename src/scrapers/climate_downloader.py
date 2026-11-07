"""Incrementally refresh country-level CHIRPS daily rainfall.

``rainfall.json`` stores pairs of ``[YYYY-MM-DD, rainfall_mm]``.  Dates are the
UTC acquisition dates supplied by the CHIRPS Earth Engine images (not local
observation timestamps); each refresh queries a start-inclusive, end-exclusive
UTC date range.  The value is the mean CHIRPS ``precipitation`` band over the
South Africa bounding rectangle, in millimetres per day.

Authentication is deliberately non-interactive.  Configure either
``EARTHENGINE_EMAIL`` plus JSON service-account key ``EARTHENGINE_KEY``, a JSON
service-account document in ``EARTHENGINE_CREDENTIALS``, or an existing local
Earth Engine credential cache.  ``EARTHENGINE_PROJECT`` selects the Cloud
project; ``global-calling-450111-e2`` is retained only as the documented legacy
default.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

try:  # Keep importing this module possible in offline/test environments.
    import ee  # type: ignore
except ImportError:  # pragma: no cover - exercised by runtime configuration
    ee = None

ROOT = Path(__file__).resolve().parents[2]
RAIN_FILE = ROOT / "src" / "resources" / "rainfall.json"
LEGACY_PROJECT = "global-calling-450111-e2"
SA_REGION_BOUNDS = [16.5, -35.0, 33.0, -22.0]
CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
LOGGER = logging.getLogger(__name__)


def _json_secret(value: str, name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must contain valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{name} must contain a JSON object.")
    return parsed


def initialise_earth_engine() -> None:
    """Initialise EE without ever calling the browser-based Authenticate API."""
    if ee is None:
        raise RuntimeError("Earth Engine Python API is not installed; install runtime dependencies before a live refresh.")

    project = os.environ.get("EARTHENGINE_PROJECT", LEGACY_PROJECT)
    email, key = os.environ.get("EARTHENGINE_EMAIL"), os.environ.get("EARTHENGINE_KEY")
    credentials_secret = os.environ.get("EARTHENGINE_CREDENTIALS")
    credentials = None

    if email or key:
        if not (email and key):
            raise RuntimeError("Set both EARTHENGINE_EMAIL and EARTHENGINE_KEY for service-account authentication.")
        key_document = _json_secret(key, "EARTHENGINE_KEY")
        credentials = ee.ServiceAccountCredentials(email, key_data=json.dumps(key_document))
    elif credentials_secret:
        document = _json_secret(credentials_secret, "EARTHENGINE_CREDENTIALS")
        service_email = document.get("client_email")
        if not isinstance(service_email, str) or not service_email:
            raise RuntimeError("EARTHENGINE_CREDENTIALS must be a service-account JSON object with client_email.")
        credentials = ee.ServiceAccountCredentials(service_email, key_data=json.dumps(document))
    else:
        cache = Path.home() / ".config" / "earthengine" / "credentials"
        if not cache.is_file():
            raise RuntimeError(
                "Live CHIRPS refresh requires non-interactive Earth Engine credentials: set "
                "EARTHENGINE_EMAIL with EARTHENGINE_KEY, EARTHENGINE_CREDENTIALS, or a local EE credential cache."
            )

    # Do not print credential objects, environment contents, or exception reprs:
    # any of them may reveal a private key.
    if credentials is None:
        ee.Initialize(project=project)
    else:
        ee.Initialize(credentials=credentials, project=project)


def _parse_rows(payload: dict[str, Any]) -> list[tuple[date, float]]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Rainfall file must contain a 'data' list.")
    parsed: list[tuple[date, float]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("Each rainfall row must be [date, rainfall_mm].")
        try:
            day = datetime.strptime(row[0], "%Y-%m-%d").date()
            rainfall = float(row[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Rainfall rows require YYYY-MM-DD dates and numeric rainfall values.") from exc
        # CHIRPS legitimately reports zero precipitation; negative/non-finite
        # values are invalid and rejected rather than silently retained.
        if not math.isfinite(rainfall) or rainfall < 0:
            raise ValueError(f"Invalid rainfall value on {day.isoformat()}.")
        parsed.append((day, rainfall))
    return parsed


def _validate_contiguous(rows: list[tuple[date, float]]) -> None:
    if not rows:
        return
    dates = [day for day, _ in rows]
    if len(set(dates)) != len(dates):
        raise ValueError("Rainfall data contains duplicate dates.")
    ordered = sorted(dates)
    if dates != ordered:
        raise ValueError("Rainfall data must be sorted by date.")
    for previous, current in zip(ordered, ordered[1:]):
        if current != previous + timedelta(days=1):
            raise ValueError(f"Rainfall data has a gap between {previous} and {current}.")


def _load_existing(path: Path) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse rainfall data at {path}.") from exc
    rows = _parse_rows(payload)
    _validate_contiguous(rows)
    return rows


def _month_chunks(start: date, end: date):
    """Yield small start-inclusive/end-exclusive chunks; never huge getInfo calls."""
    cursor = start
    while cursor < end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        chunk_end = min(next_month, end)
        yield cursor, chunk_end
        cursor = chunk_end


def _latest_available_date(today: date) -> date:
    """Return the newest published CHIRPS UTC date, never looking past today."""
    assert ee is not None
    collection = ee.ImageCollection(CHIRPS_COLLECTION).filterDate("2000-01-01", (today + timedelta(days=1)).isoformat())
    timestamp = collection.aggregate_max("system:time_start").getInfo()
    if timestamp is None:
        raise RuntimeError("Earth Engine returned an empty CHIRPS collection.")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise RuntimeError("Earth Engine returned an invalid CHIRPS latest-image timestamp.")
    try:
        return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError) as exc:
        raise RuntimeError("Earth Engine returned an invalid CHIRPS latest-image timestamp.") from exc


def _fetch_chunk(start: date, end: date) -> list[tuple[date, float]]:
    assert ee is not None
    region = ee.Geometry.Rectangle(SA_REGION_BOUNDS)
    collection = ee.ImageCollection(CHIRPS_COLLECTION).filterDate(start.isoformat(), end.isoformat()).filterBounds(region)

    def extract(image):
        rainfall = image.select("precipitation").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=5000, maxPixels=10_000_000_000
        ).get("precipitation")
        return image.set({"date": image.date().format("YYYY-MM-dd"), "rainfall_mm": rainfall})

    values = collection.map(extract).reduceColumns(ee.Reducer.toList(2), ["date", "rainfall_mm"]).get("list").getInfo()
    if not isinstance(values, list):
        raise RuntimeError(f"Earth Engine returned no usable CHIRPS rows for {start} to {end}.")
    return _parse_rows({"data": values})


def _atomic_write(path: Path, rows: list[tuple[date, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"data": [[day.isoformat(), rainfall] for day, rainfall in rows]}
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(payload, temporary, indent=4, allow_nan=False)
        temporary.write("\n")
        temp_path = Path(temporary.name)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def document_downloader(path: Path = RAIN_FILE, today: date | None = None) -> int:
    """Fetch all missing complete UTC days and atomically merge them.

    Raises on a missing/duplicate day, invalid value, credentials issue, or EE
    failure.  The existing file is untouched unless the complete refresh passes
    validation.
    """
    existing = _load_existing(path)
    start = existing[-1][0] + timedelta(days=1) if existing else date(2000, 1, 1)
    requested_today = today or date.today()
    initialise_earth_engine()
    latest_available = _latest_available_date(requested_today)
    # The latest image is itself complete; make it part of the end-exclusive range.
    end = min(requested_today, latest_available + timedelta(days=1))
    if start >= end:
        source_date = existing[-1][0].isoformat() if existing else "none"
        LOGGER.info("No new CHIRPS data available; existing source date is %s.", source_date)
        return 0
    fetched: list[tuple[date, float]] = []
    for chunk_start, chunk_end in _month_chunks(start, end):
        chunk = _fetch_chunk(chunk_start, chunk_end)
        _validate_contiguous(chunk)
        expected = (chunk_end - chunk_start).days
        if len(chunk) != expected or not chunk or chunk[0][0] != chunk_start or chunk[-1][0] != chunk_end - timedelta(days=1):
            raise RuntimeError(f"Incomplete CHIRPS response for {chunk_start} to {chunk_end}; refusing partial update.")
        fetched.extend(chunk)
    merged = existing + fetched
    _validate_contiguous(merged)
    _atomic_write(path, merged)
    return len(fetched)


if __name__ == "__main__":
    updated = document_downloader()
    print(f"CHIRPS rainfall updated: {updated} day(s).")
