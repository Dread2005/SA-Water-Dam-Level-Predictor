"""Folium maps for rainfall forecasts, joined to known dam coordinates conservatively."""
from __future__ import annotations

from html import escape
from pathlib import Path
import re

import pandas as pd


def _normalise(value: object) -> str:
    """Canonicalize names while treating a terminal 'Dam' as a descriptor.

    Both source tables commonly differ only by that terminal word (for example,
    ``Bon Accord Dam`` versus ``Bon Accord``).  This is still an exact match of
    the remaining full name; non-unique canonical coordinate rows are discarded.
    """
    text = re.sub(r"[^a-z0-9]", "", str(value).lower())
    return text[:-3] if text.endswith("dam") else text


def matched_dams(dam_path: str | Path, locations_path: str | Path) -> pd.DataFrame:
    dams = pd.read_csv(dam_path).copy()
    locations = pd.read_csv(locations_path)
    dam_name_column = "Dam" if "Dam" in dams else "willDam"
    if dam_name_column not in dams:
        raise ValueError("dam source needs a Dam or willDam column")
    required = {"Name of dam", "Country", "Decimal degree latitude", "Decimal degree longitude"}
    if not required.issubset(locations.columns):
        raise ValueError(f"location source missing {sorted(required - set(locations.columns))}")
    dams = dams[dams[dam_name_column].astype(str).str.strip().str.lower().ne("total")].copy()
    dams["name_key"] = dams[dam_name_column].map(_normalise)
    geo = locations.loc[locations["Country"].astype(str).str.strip().eq("South Africa"), ["Name of dam", "Decimal degree latitude", "Decimal degree longitude"]].copy()
    geo["name_key"] = geo["Name of dam"].map(_normalise)
    geo["latitude"] = pd.to_numeric(geo["Decimal degree latitude"], errors="coerce")
    geo["longitude"] = pd.to_numeric(geo["Decimal degree longitude"], errors="coerce")
    geo = geo.dropna(subset=["latitude", "longitude"])
    # A canonical name mapping to multiple locations is ambiguous: omit it.
    geo = geo.loc[~geo.duplicated("name_key", keep=False)]
    joined = dams.merge(geo[["name_key", "latitude", "longitude"]], how="inner", on="name_key")
    joined = joined.rename(columns={dam_name_column: "dam_name"})
    return joined[["dam_name", "latitude", "longitude", *[c for c in ["This Week", "Last Week", "Last Year"] if c in joined]]]


def write_forecast_map(dams: pd.DataFrame, forecast: dict, horizon: int, output_path: str | Path) -> Path:
    """Write a map that repeats the national rainfall estimate, never a dam forecast."""
    try:
        import folium
    except ImportError as exc:
        raise RuntimeError("Folium is required to generate forecast maps. Install project dependencies.") from exc
    key = f"{horizon}d"
    amount = forecast["forecasts"][key]["predicted_cumulative_rainfall_mm"]
    title = f"{horizon}-day country-level rainfall estimate: {amount:.1f} mm"
    fmap = folium.Map(location=[-29.0, 24.0], zoom_start=5, tiles="OpenStreetMap")
    for row in dams.itertuples(index=False):
        weekly = getattr(row, "_3", None) if "This Week" in dams else None
        dam_text = f"<b>{escape(str(row.dam_name))}</b><br>{escape(title)}<br>Not a dam-level forecast."
        if weekly is not None:
            dam_text += f"<br>Reported current level: {escape(str(weekly))}%"
        folium.CircleMarker([row.latitude, row.longitude], radius=5, color="#1565c0", fill=True, fill_opacity=.75, popup=folium.Popup(dam_text, max_width=260)).add_to(fmap)
    fmap.get_root().html.add_child(folium.Element(f"<h3 style='position:fixed;top:8px;left:50px;z-index:9999;background:white;padding:8px'>{escape(title)}<br><small>Markers show dams with exact normalized-name coordinate matches only.</small></h3>"))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(output)
    return output
