import pytest

from microns_finder.query import find_cells, parse_areas, proofreading_summary, split_request


def roots(result):
    return set(result.cells.root_id)


def test_astrocyte_in_l1(cells):
    res = find_cells(cells, "astrocyte", layer="L1", n=10)
    assert roots(res) == {101, 102}
    assert res.pool_size == 2
    assert res.cells.iloc[0].root_id == 102  # proofread astrocyte first


def test_white_matter_note(cells):
    res = find_cells(cells, "astrocyte", layer="white matter", n=10)
    assert roots(res) == {104}
    assert any("white matter" in note for note in res.notes)


def test_merged_and_empty_segments_excluded(cells):
    res = find_cells(cells, "L5 ET", n=10)
    assert res.pool_size == 0
    res = find_cells(cells, "L5 ET", n=10, allow_merged=True)
    assert roots(res) == {113}


def test_label_modes(cells):
    assert roots(find_cells(cells, "neurogliaform", n=10)) == {109, 110}
    assert roots(find_cells(cells, "neurogliaform", labels="consensus", n=10)) == {109}
    assert roots(find_cells(cells, "neurogliaform", labels="meso", n=10)) == {109}


def test_agreeing_cells_ranked_first(cells):
    # 110 is proofread but the models disagree; 109 is unproofread but they agree.
    res = find_cells(cells, "neurogliaform", n=1)
    assert res.cells.iloc[0].root_id == 109
    assert any("consensus" in note for note in res.notes)


def test_proofread_filters(cells):
    assert roots(find_cells(cells, "pyramidal", proofread="full", n=10)) == {108}
    assert roots(find_cells(cells, "astrocyte", proofread="any", n=10)) == {102}
    assert roots(find_cells(cells, "astrocyte", proofread="full", n=10)) == {102}


def test_area_expert_functional(cells):
    assert roots(find_cells(cells, "basket", area="HVA", n=10)) == {112}
    assert roots(find_cells(cells, "basket", expert=True, n=10)) == {111}
    assert roots(find_cells(cells, "basket", functional=True, n=10)) == {112}


def test_where_depth_exclude(cells):
    assert roots(find_cells(cells, where={"mtype": "L2a"}, n=10)) == {107}
    assert roots(find_cells(cells, "astrocyte", depth=(0, 100), n=10)) == {101, 102}
    assert roots(find_cells(cells, "astrocyte", layer="L1", exclude=[102], n=10)) == {101}
    with pytest.raises(ValueError):
        find_cells(cells, where={"no_such_column": "x"})


def test_seed_is_reproducible(cells):
    a = find_cells(cells, "astrocyte", n=2, seed=3, prefer_proofread=False)
    b = find_cells(cells, "astrocyte", n=2, seed=3, prefer_proofread=False)
    assert list(a.cells.root_id) == list(b.cells.root_id)


def test_no_match_note(cells):
    res = find_cells(cells, "microglia", n=3)
    assert res.pool_size == 0 and res.notes


@pytest.mark.parametrize(
    "text, term, layers, areas",
    [
        ("astrocyte in layer 1", "astrocyte", ["L1"], None),
        ("astrocyte in the white matter", "astrocyte", ["WM"], None),
        ("oligodendrocyte in L2/3", "oligodendrocyte", ["L2", "L3"], None),
        ("basket cell in V1", "basket cell", None, ["V1"]),
        ("L5 ET in layer 6 in RL", "L5 ET", ["L6"], ["RL"]),
        ("L5 ET", "L5 ET", None, None),
        ("astrocytes in L6b", "astrocytes", ["L6"], None),
        ("basket cell in layers 2 and 3", "basket cell", ["L2", "L3"], None),
        ("pyramidal in layer 2-3", "pyramidal", ["L2", "L3"], None),
        ("astrocyte in layer 2/3 of V1", "astrocyte", ["L2", "L3"], ["V1"]),
        ("astrocyte in V1 layer 4", "astrocyte", ["L4"], ["V1"]),
        ("oligodendrocyte in the white matter in AL", "oligodendrocyte", ["WM"], ["AL"]),
        ("L4 basket cell", "basket cell", ["L4"], None),
        ("L2/3 interneuron", "interneuron", ["L2", "L3"], None),
        ("L5 Martinotti cell", "Martinotti cell", ["L5"], None),
        ("layer 5 ET", "layer 5 ET", None, None),
        ("L6 WM", "L6 WM", None, None),
        ("a basket cell in layer 4", "a basket cell", ["L4"], None),
    ],
)
def test_split_request(text, term, layers, areas):
    assert split_request(text) == (term, layers, areas)


def test_parse_areas():
    assert parse_areas("hva") == ["RL", "AL", "LM"]
    with pytest.raises(ValueError):
        parse_areas("V2")


def test_cells_near_layer_boundary_ranked_last(cells):
    cells = cells.copy()
    near = cells.root_id == 102  # proofread L1 astrocyte, moved to 5 µm above the L1/L2 boundary
    cells.loc[near, "depth_um"] = 80.0
    res = find_cells(cells, "astrocyte", layer="L1", n=2)
    assert list(res.cells.root_id) == [101, 102]


def test_position_defined_term_uses_its_layer(cells):
    assert roots(find_cells(cells, "L1 interneuron", n=10)) == {109, 110}
    assert roots(find_cells(cells, "L1 interneuron", layer="L2", n=10)) == {117}


def test_outer_edges_only():
    from microns_finder.query import _outer_edges

    assert _outer_edges(["L2", "L3"]) == [85.0, 250.0]
    assert _outer_edges(["L1"]) == [85.0]
    assert _outer_edges(["WM"]) == [720.0]


def test_contradicting_labels_ranked_last_and_dropped_by_consensus(cells):
    res = find_cells(cells, "interneuron", layer="L2", n=10)
    assert 117 in roots(res)
    res = find_cells(cells, "interneuron", n=10)
    assert res.cells.iloc[-1].root_id == 117
    assert any("contradicts" in note for note in res.notes)
    assert 117 not in roots(find_cells(cells, "interneuron", labels="consensus", n=10))


def test_negative_n_rejected(cells):
    with pytest.raises(ValueError):
        find_cells(cells, "astrocyte", n=-1)


def test_proofreading_summary_without_strategy(cells):
    row = next(cells[cells.root_id == 110].itertuples())  # proofread, but no strategy recorded
    assert proofreading_summary(row) == "dendrite clean, axon clean"
