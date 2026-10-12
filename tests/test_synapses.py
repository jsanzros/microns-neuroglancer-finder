"""Synapses between cell types, on the synthetic table and synapses in conftest.py."""

import json
import urllib.parse

from microns_finder import service, synapses
from microns_finder.links import SYNAPSE_ZOOM, connection_links
from microns_finder.synapses import find_synapses


def pairs(result):
    return [(int(c.pre.root_id), int(c.post.root_id)) for c in result.connections]


def _state(url):
    return json.loads(urllib.parse.unquote(url.split("#!", 1)[1]))


def test_label_agreement_ranked_first(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "neurogliaform", "basket", n=5)
    # Every label system calls 109 neurogliaform; 110 has a proofread axon but its labels disagree.
    assert pairs(res) == [(109, 111), (110, 112)]
    assert (res.n_pairs, res.n_synapses) == (2, 4)
    assert synapse_client.materialize.calls == [{"pre_ids": {109, 110}, "post_ids": {111, 112}}]
    assert any("nucleus 9" in note and "isn't proofread" in note for note in res.notes)


def test_proofread_axons_ranked_next(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "pyramidal", "basket", n=5)
    # 108's axon is proofread, so its one synapse beats 107's two.
    assert pairs(res) == [(108, 111), (107, 112)]


def test_min_synapses_and_largest_synapse_first(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "neurogliaform", "basket", n=5, min_synapses=2)
    [conn] = res.connections
    assert list(conn.synapses.id) == [2, 1, 3]  # sizes 900, 500, 300


def test_no_synapses_and_autapses(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "basket", "neurogliaform")
    assert res.connections == [] and any("No synapses" in note for note in res.notes)
    res = find_synapses(synapse_client, cells, "basket", "basket", n=5)  # only an autapse links them
    assert res.connections == []


def test_cell_limit_keeps_best_proofread_axons(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "pyramidal", "basket", max_cells=1)
    assert synapse_client.materialize.calls[-1]["pre_ids"] == {108}
    assert any("the 1 best of the 2 presynaptic" in note and "--max-cells" in note for note in res.notes)


def test_search_widens_until_enough_pairs(cells, synapse_client, monkeypatch):
    monkeypatch.setattr(synapses, "SEARCH_STEPS", (1,))
    res = find_synapses(synapse_client, cells, "neurogliaform", "basket", n=2, max_cells=2)
    sizes = [(len(c["pre_ids"]), len(c["post_ids"])) for c in synapse_client.materialize.calls]
    assert sizes == [(1, 1), (2, 2)] and len(res.connections) == 2


def test_connection_links_zoom_on_each_synapse(cells, synapse_client):
    res = find_synapses(synapse_client, cells, "neurogliaform", "basket", min_synapses=2)
    overview, zooms = connection_links(res.connections[0], client=None, zoom=2)
    state = _state(overview)
    assert [layer["name"] for layer in state["layers"]] == ["imagery", "cells", "somata", "synapses"]
    assert sorted(state["layers"][1]["segments"]) == ["109", "111"]
    marks = state["layers"][3]["annotations"]
    assert len(marks) == 3 and all(sorted(a["segments"][0]) == ["109", "111"] for a in marks)
    assert state["position"] == [100002.0, 100000.0, 20000.0]  # opens at the largest synapse
    assert len(zooms) == 2
    for url, synapse_id in zip(zooms, [2, 1]):
        zoomed = _state(url)
        assert zoomed["position"] == [100000.0 + synapse_id, 100000.0, 20000.0]
        assert zoomed["crossSectionScale"] == SYNAPSE_ZOOM["scale_imagery"]
        assert zoomed["projectionScale"] == SYNAPSE_ZOOM["scale_3d"]


def test_service_parses_each_side(offline_finder):
    data = service.synapses(offline_finder, "neurogliaform in layer 1 onto basket cell in V1", n=2, zoom=1)
    assert data["request"] == {"pre": "neurogliaform in layer 1", "post": "basket cell in V1"}
    assert data["pre"]["term"]["key"] == "neurogliaform" and data["params"]["pre_layer"] == ["L1"]
    assert data["post"]["term"]["key"] == "basket" and data["params"]["post_area"] == ["V1"]
    # 112 is in RL, so only the pair onto 111 remains.
    assert [(p["pre"]["root_id"], p["post"]["root_id"]) for p in data["pairs"]] == [("109", "111")]
    [pair] = data["pairs"]
    assert pair["synapses"][0] == {"id": 2, "size": 900, "position_vx": [100002, 100000, 20000]}
    assert [z["synapse_id"] for z in pair["zoom_links"]] == [2]


def test_service_errors(offline_finder):
    assert "onto" in service.synapses(offline_finder, "neurogliaform and basket")["error"]
    data = service.synapses(offline_finder, pre="neurogliaform", post="astrocite")
    assert "astrocyte" in data["suggestions"]
