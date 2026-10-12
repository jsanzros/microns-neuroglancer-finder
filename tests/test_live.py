"""Checks against the real MICrONS data. Run with: pytest -m live

They download the cell table on first run (~10 s) and need a CAVE token.
"""

import pytest

from microns_finder import Finder
from microns_finder.layers import current_boundaries, derive_boundaries
from microns_finder.vocab import load_terms

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def finder():
    return Finder()


@pytest.mark.parametrize("term", [t.key for t in load_terms()])
def test_every_term_finds_cells(finder, term):
    assert finder.find(term, n=1).pool_size > 0


@pytest.mark.parametrize("term", [t.key for t in load_terms() if len(t.definitions) > 1])
def test_consensus_finds_cells(finder, term):
    assert finder.find(term, labels="consensus", n=1).pool_size > 0


def test_layer_boundaries_still_match_data(finder):
    derived = derive_boundaries(finder.cells)
    for name, value in current_boundaries().items():
        assert abs(derived[name] - value) <= 15, (name, derived[name], value)


@pytest.mark.parametrize(
    "subclass, layers, minimum",
    [("23P", {"L2", "L3"}, 0.9), ("4P", {"L4"}, 0.8), ("5P-IT", {"L5"}, 0.8), ("6P-CT", {"L6"}, 0.9)],
)
def test_subclasses_sit_in_their_layers(finder, subclass, layers, minimum):
    cells = finder.cells[(finder.cells.cell_type == subclass) & (finder.cells.broad_type == "excitatory")]
    assert cells.layer.isin(layers).mean() >= minimum


def test_user_examples(finder):
    for request, layer in [
        ("oligodendrocyte", "L2"),
        ("astrocyte", "WM"),
        ("astrocyte", "L1"),
        ("neurogliaform", None),
        ("basket", None),
        ("pyramidal", "L2"),
    ]:
        res = finder.find(request, layer=layer, n=3)
        assert len(res.cells) == 3, request
        if layer:
            assert set(res.cells.layer) == {layer}


def test_short_link_round_trip(finder):
    res = finder.find("astrocyte", layer="L1", n=2)
    url = finder.link(res)
    assert "nglstate/api/v1/" in url
    state = finder.client.state.get_state_json(int(url.rsplit("/", 1)[1]))
    first = res.cells.iloc[0]
    assert state["position"] == [float(first.x), float(first.y), float(first.z)]
    seg = next(layer for layer in state["layers"] if layer["name"] == "cells")
    assert {int(s) for s in seg["segments"]} == {int(r) for r in res.cells.root_id}
