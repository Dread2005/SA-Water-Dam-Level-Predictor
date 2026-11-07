"""Download the DWS weekly provincial dam tables without partial overwrites."""
from __future__ import annotations

import io
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILE = ROOT / "src" / "resources" / "all_dams_weekly.csv"
PROVINCES = ("G", "L", "M", "NW", "FS", "KZN", "EC", "NC", "WC")
DWS_URL = "https://www.dws.gov.za/Hydrology/Weekly/ProvinceWeek.aspx?region={province}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dam-predictor/1.0; +https://github.com/)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUIRED_COLUMNS = {"Dam", "River", "This Week", "Last Week", "Last Year"}


def get_with_retry(
    url: str,
    *,
    session: requests.Session | requests.api = requests,
    retries: int = 4,
    timeout: tuple[float, float] = (10, 30),
    backoff: float = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Fetch a page with bounded retries for transient DWS/network failures."""
    last_error: requests.RequestException | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None
            if status is None or (status != 429 and not 500 <= status < 600):
                raise RuntimeError(f"DWS returned non-retryable HTTP status {status} for {url}.") from exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
        if attempt < retries - 1:
            sleep(backoff * (2**attempt))
    raise RuntimeError(f"DWS request failed after {retries} attempt(s) for {url}.") from last_error


def _choose_dam_table(html: str) -> pd.DataFrame:
    """Select the table by DWS schema, never by a fragile positional index."""
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError as exc:
        raise RuntimeError("DWS page did not contain any HTML tables.") from exc
    matches: list[pd.DataFrame] = []
    for table in tables:
        frame = table.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [" ".join(str(x) for x in column if str(x) != "nan").strip() for column in frame.columns]
        frame.columns = [str(column).strip() for column in frame.columns]
        if REQUIRED_COLUMNS.issubset(frame.columns):
            cleaned = frame.dropna(how="all")
            cleaned = cleaned[cleaned["Dam"].astype(str).str.strip().str.lower().ne("dam")]
            if not cleaned.empty:
                matches.append(cleaned)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one DWS dam table matching {sorted(REQUIRED_COLUMNS)}, found {len(matches)}.")
    return matches[0]


def DWS_Data(url: str, **request_options) -> pd.DataFrame:
    return _choose_dam_table(get_with_retry(url, **request_options))


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as temporary:
        frame.to_csv(temporary, index=False)
        temp_path = Path(temporary.name)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def all_dam_data(output_file: Path = OUTPUT_FILE, *, fetcher: Callable[[str], pd.DataFrame] = DWS_Data) -> pd.DataFrame:
    """Fetch every province and replace output only after all succeed."""
    frames: list[pd.DataFrame] = []
    for province in PROVINCES:
        url = DWS_URL.format(province=province)
        try:
            frame = fetcher(url)
        except Exception as exc:
            raise RuntimeError(f"Could not fetch DWS data for province {province}; existing output was preserved.") from exc
        if not REQUIRED_COLUMNS.issubset(frame.columns) or frame.empty:
            raise RuntimeError(f"DWS data for province {province} has no usable dam-table schema; existing output was preserved.")
        frames.append(frame)
    full_df = pd.concat(frames, ignore_index=True)
    if full_df.empty:
        raise RuntimeError("DWS returned no dam rows; existing output was preserved.")
    _atomic_csv(output_file, full_df)
    return full_df


if __name__ == "__main__":
    frame = all_dam_data()
    print(f"Dam data updated: {len(frame)} row(s) from {len(PROVINCES)} provinces.")
