"""The no-token path: the prebuilt cell table snapshot and Finder without CAVE."""

import hashlib
import json
import urllib.parse
import warnings

import pytest

from microns_finder import config, data
from microns_finder.finder import NO_TOKEN_NOTE, Finder


@pytest.fixture
def snapshot(cells, tmp_path, monkeypatch):
    """A snapshot file of the synthetic table, an empty cache, and no CAVE token."""
    src = tmp_path / "snapshot.parquet"
    cells.to_parquet(src, index=False)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    monkeypatch.setenv("MICRONS_FINDER_CACHE", str(tmp_path / "cache"))
    monkeypatch.setitem(config.SNAPSHOTS, (1926, data.CACHE_SCHEMA), (src.as_uri(), sha))

    def no_token(version):
        raise RuntimeError("no token")

    monkeypatch.setattr(data, "make_client", no_token)
    monkeypatch.setattr("microns_finder.finder.make_client", no_token)
    return src


def test_download_checks_and_records(snapshot):
    df = data.download_snapshot(1926)
    assert len(df) == len(data.pd.read_parquet(snapshot))
    info = data.cache_info(1926)
    assert info["source"] == "snapshot" and info["rows"] == len(df)


def test_corrupted_download_is_rejected(snapshot, monkeypatch):
    url, _ = config.SNAPSHOTS[(1926, data.CACHE_SCHEMA)]
    monkeypatch.setitem(config.SNAPSHOTS, (1926, data.CACHE_SCHEMA), (url, "0" * 64))
    with pytest.raises(RuntimeError, match="corrupted"):
        data.download_snapshot(1926)
    assert data.cache_info(1926) is None


def test_auto_falls_back_without_token(snapshot):
    df = data.load_cells(1926)
    assert data.cache_info(1926)["source"] == "snapshot" and len(df) > 0


def test_cave_source_does_not_fall_back(snapshot):
    with pytest.raises(RuntimeError):
        data.load_cells(1926, source="cave")


def test_no_snapshot_for_other_versions(snapshot):
    with pytest.raises(RuntimeError, match="no prebuilt"):
        data.load_cells(1822)


def test_finder_without_token(snapshot):
    f = Finder()
    assert f.online is False
    res = f.find("astrocyte", layer="L1", n=2)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        url = f.link(res, synapses=True)
    messages = [str(w.message) for w in caught]
    assert NO_TOKEN_NOTE in messages and any("cells only" in m for m in messages)
    state = json.loads(urllib.parse.unquote(url.split("#!", 1)[1]))
    assert sorted(state["layers"][1]["segments"]) == sorted(str(r) for r in res.cells.root_id)
    with pytest.raises(ValueError, match="CAVE token"):
        f.synapses("basket", "pyramidal")


def test_service_reports_no_token(snapshot):
    from microns_finder import service

    payload = service.find(Finder(), "astrocyte in layer 1", n=1)
    assert payload["link"] and NO_TOKEN_NOTE in payload["notes"]
    syn = service.synapses(Finder(), "basket onto pyramidal")
    assert "error" in syn and "CAVE token" in syn["error"]
