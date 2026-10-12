import json
import urllib.parse

from microns_finder.links import build_state, cell_label, make_link
from microns_finder.query import find_cells


def _state(url):
    fragment = urllib.parse.unquote(url.split("#!", 1)[1])
    return json.loads(fragment)


def test_offline_link_contents(cells):
    res = find_cells(cells, "astrocyte", layer="L1", n=2)
    url = make_link(res.cells, client=None, title="test")
    assert url.startswith("https://spelunker.cave-explorer.org/")
    state = _state(url)
    names = [layer["name"] for layer in state["layers"]]
    assert names == ["imagery", "cells", "somata"]
    seg = state["layers"][1]
    assert sorted(seg["segments"]) == ["101", "102"]
    somata = state["layers"][2]["annotations"]
    assert len(somata) == 2 and all("nucleus" in a["description"] for a in somata)
    first = res.cells.iloc[0]
    assert state["position"] == [float(first.x), float(first.y), float(first.z)]
    assert state["title"] == "test"


def test_cell_label(cells):
    row = next(cells[cells.root_id == 108].itertuples())
    label = cell_label(row)
    assert label.startswith("23P / L3a / L3IT | L3 200 µm | V1")
    assert "axon fully_extended" in label and "nucleus 8" in label


def test_duplicate_roots_shown_once(cells):
    rows = cells[cells.root_id == 113]
    vs = build_state(rows, client=None)
    assert len(vs.get_layer("cells").segments) == 1
