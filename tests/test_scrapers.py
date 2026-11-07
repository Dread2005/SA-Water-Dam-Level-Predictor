import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.scrapers import climate_downloader as climate
from src.scrapers import dws_scraper as dws


def write_rainfall(path: Path, rows):
    path.write_text(json.dumps({"data": rows}), encoding="utf-8")


def test_climate_missing_credentials_fails_before_fetch(monkeypatch, tmp_path):
    rainfall = tmp_path / "rainfall.json"
    write_rainfall(rainfall, [["2026-06-30", 1.0]])
    monkeypatch.delenv("EARTHENGINE_EMAIL", raising=False)
    monkeypatch.delenv("EARTHENGINE_KEY", raising=False)
    monkeypatch.delenv("EARTHENGINE_CREDENTIALS", raising=False)
    monkeypatch.setattr(climate.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(climate, "ee", object())
    monkeypatch.setattr(climate, "_fetch_chunk", lambda *_: pytest.fail("fetch must not occur"))
    with pytest.raises(RuntimeError, match="non-interactive"):
        climate.document_downloader(rainfall, today=date(2026, 7, 2))
    assert json.loads(rainfall.read_text())["data"] == [["2026-06-30", 1.0]]


def test_climate_incremental_month_chunks_atomic_merge(monkeypatch, tmp_path):
    rainfall = tmp_path / "rainfall.json"
    write_rainfall(rainfall, [["2026-06-30", 1.0]])
    requested = []
    monkeypatch.setattr(climate, "initialise_earth_engine", lambda: None)
    monkeypatch.setattr(climate, "_latest_available_date", lambda today: date(2026, 7, 2))

    def fetch(start, end):
        requested.append((start, end))
        return [(start, 0.0), (start.replace(day=start.day + 1), 2.0)]

    monkeypatch.setattr(climate, "_fetch_chunk", fetch)
    assert climate.document_downloader(rainfall, today=date(2026, 7, 3)) == 2
    assert requested == [(date(2026, 7, 1), date(2026, 7, 3))]
    assert json.loads(rainfall.read_text())["data"] == [["2026-06-30", 1.0], ["2026-07-01", 0.0], ["2026-07-02", 2.0]]


def test_climate_rejects_incomplete_response_without_overwrite(monkeypatch, tmp_path):
    rainfall = tmp_path / "rainfall.json"
    original = {"data": [["2026-06-30", 1.0]]}
    rainfall.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(climate, "initialise_earth_engine", lambda: None)
    monkeypatch.setattr(climate, "_latest_available_date", lambda today: date(2026, 7, 2))
    monkeypatch.setattr(climate, "_fetch_chunk", lambda *_: [(date(2026, 7, 1), 1.0)])
    with pytest.raises(RuntimeError, match="Incomplete"):
        climate.document_downloader(rainfall, today=date(2026, 7, 3))
    assert json.loads(rainfall.read_text()) == original


def test_climate_stops_at_latest_published_day(monkeypatch, tmp_path):
    rainfall = tmp_path / "rainfall.json"
    original = {"data": [["2026-06-30", 1.0]]}
    rainfall.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(climate, "initialise_earth_engine", lambda: None)
    monkeypatch.setattr(climate, "_latest_available_date", lambda today: date(2026, 6, 30))
    monkeypatch.setattr(climate, "_fetch_chunk", lambda *_: pytest.fail("no newer data must not be fetched"))

    assert climate.document_downloader(rainfall, today=date(2026, 7, 3)) == 0
    assert json.loads(rainfall.read_text()) == original


def test_climate_latest_available_uses_aggregate_max_and_fails_empty(monkeypatch):
    calls = []

    class Aggregate:
        def __init__(self, value):
            self.value = value

        def getInfo(self):
            return self.value

    class Collection:
        def filterDate(self, start, end):
            calls.append((start, end))
            return self

        def aggregate_max(self, property_name):
            assert property_name == "system:time_start"
            return Aggregate(1780358400000)  # 2026-06-02T00:00:00Z

    class EarthEngine:
        def ImageCollection(self, collection_name):
            assert collection_name == climate.CHIRPS_COLLECTION
            return Collection()

    monkeypatch.setattr(climate, "ee", EarthEngine())
    assert climate._latest_available_date(date(2026, 7, 3)) == date(2026, 6, 2)
    assert calls == [("2000-01-01", "2026-07-04")]

    class EmptyCollection(Collection):
        def aggregate_max(self, property_name):
            return Aggregate(None)

    monkeypatch.setattr(climate, "ee", type("EmptyEarthEngine", (), {"ImageCollection": lambda self, _: EmptyCollection()})())
    with pytest.raises(RuntimeError, match="empty CHIRPS"):
        climate._latest_available_date(date(2026, 7, 3))


def test_climate_rejects_duplicate_and_invalid_values(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    write_rainfall(duplicate, [["2026-06-30", 1], ["2026-06-30", 2]])
    with pytest.raises(ValueError, match="duplicate"):
        climate.document_downloader(duplicate, today=date(2026, 7, 1))
    with pytest.raises(ValueError, match="Invalid rainfall"):
        climate._parse_rows({"data": [["2026-07-01", float("nan")]]})


def dam_html():
    return """<table><tr><th>Noise</th></tr><tr><td>x</td></tr></table>
    <table><tr><th>Dam</th><th>River</th><th>This Week</th><th>Last Week</th><th>Last Year</th></tr>
    <tr><td>Alpha Dam</td><td>Alpha River</td><td>52</td><td>51</td><td>50</td></tr></table>"""


def test_dws_selects_schema_table_and_retries_transient_failure():
    class Response:
        text = dam_html()
        def raise_for_status(self):
            return None

    class Session:
        def __init__(self): self.calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise requests.Timeout("slow")
            assert kwargs["timeout"] == (10, 30)
            return Response()

    session = Session()
    table = dws.DWS_Data("https://example.test", session=session, sleep=lambda _: None)
    assert session.calls == 2
    assert table["Dam"].tolist() == ["Alpha Dam"]


def test_dws_preserves_existing_csv_when_a_province_fails(tmp_path):
    output = tmp_path / "dams.csv"
    output.write_text("old,data\n1,2\n", encoding="utf-8")
    calls = 0
    def fetcher(url):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("down")
        return pd.DataFrame({"Dam": ["A"], "River": ["R"], "This Week": [1], "Last Week": [1], "Last Year": [1]})

    with pytest.raises(RuntimeError, match="province M"):
        dws.all_dam_data(output, fetcher=fetcher)
    assert output.read_text(encoding="utf-8") == "old,data\n1,2\n"


def test_run_live_accepts_email_and_key_and_rejects_incomplete_pair(monkeypatch):
    import orchestrator.run_pipeline as pipeline
    calls = []
    monkeypatch.setattr(pipeline.Path, "home", classmethod(lambda cls: Path("/definitely/no/cache")))
    monkeypatch.setattr(pipeline.subprocess, "run", lambda command, **kwargs: calls.append(command))
    monkeypatch.setenv("EARTHENGINE_EMAIL", "service@example.test")
    monkeypatch.setenv("EARTHENGINE_KEY", '{"private_key":"not-real"}')
    monkeypatch.delenv("EARTHENGINE_CREDENTIALS", raising=False)
    pipeline.run_live("weekly")
    assert calls == [[pipeline.sys.executable, "src/scrapers/climate_downloader.py"], [pipeline.sys.executable, "src/scrapers/dws_scraper.py"]]
    monkeypatch.delenv("EARTHENGINE_KEY")
    with pytest.raises(RuntimeError, match="non-interactive"):
        pipeline.run_live("daily")
