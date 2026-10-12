import pytest

from microns_finder.vocab import LABEL_SYSTEMS, UnknownTermError, _variants, get_term, load_terms, resolve


def test_keys_unique():
    keys = [t.key for t in load_terms()]
    assert len(keys) == len(set(keys))


def test_no_synonym_collisions():
    """Every name (and its normalized variants) must point to exactly one term."""
    owner = {}
    clashes = []
    for term in load_terms():
        for name in (term.key, term.label, *term.synonyms):
            form = _variants(name)[0]
            if form in owner and owner[form] != term.key:
                clashes.append((name, owner[form], term.key))
            owner.setdefault(form, term.key)
    assert not clashes, clashes


def test_every_term_has_a_filter():
    for term in load_terms():
        assert term.broad_type or term.definitions, term.key
        for system in term.definitions:
            assert system in LABEL_SYSTEMS


@pytest.mark.parametrize(
    "text, key",
    [
        ("astrocyte", "astrocyte"),
        ("Astrocytes", "astrocyte"),
        ("an oligodendrocyte", "oligodendrocyte"),
        ("oligos", "oligodendrocyte"),
        ("OPCs", "opc"),
        ("NG2 glia", "opc"),
        ("microglia", "microglia"),
        ("neurogliaform cells", "neurogliaform"),
        ("neuroglia form", "neurogliaform"),
        ("neuroglia", "glia"),
        ("basket cell", "basket"),
        ("basket cells", "basket"),
        ("Martinotti cells", "martinotti"),
        ("chandelier neurons", "chandelier"),
        ("axo-axonic", "chandelier"),
        ("VIP interneuron", "bipolar"),
        ("SST", "sst"),
        ("L5 PT", "l5_et"),
        ("thick-tufted", "l5_et"),
        ("L2/3 pyramidal cells", "l23_pyramidal"),
        ("pyramidal cell", "excitatory"),
        ("interneurons", "inhibitory"),
        ("L6 corticothalamic", "l6_ct"),
        ("PV basket cell", "pv_basket"),
        ("PV+ basket cell", "pv_basket"),
        ("CCK basket cell", "alt_basket"),
        ("layer 5 ET", "l5_et"),
        ("ET", "l5_et"),
        ("L5 pyramidal", "l5_pyramidal"),
        ("L6 pyramidal cells", "l6_pyramidal"),
        ("Pvalb", "pv"),
        ("somatostatin-positive", "sst"),
        ("L6b neuron", "l6_wm"),
        ("L2-3 pyramidal", "l23_pyramidal"),
        ("layer 1 interneurons", "l1_interneuron"),
    ],
)
def test_resolve(text, key):
    assert resolve(text).key == key


def test_resolve_raw_label():
    term = resolve("L2a", {"mtype": {"L2a", "L2b"}})
    assert term.definitions == {"mtype": ("L2a",)}


def test_unknown_term_suggests():
    with pytest.raises(UnknownTermError) as err:
        resolve("astrocite")
    assert "astrocyte" in err.value.suggestions


def test_systems_for_modes():
    basket = get_term("basket")
    assert basket.systems_for("subclass") == ["subclass"]
    assert basket.systems_for("meso") == ["meso"]
    assert basket.systems_for("consensus") == ["subclass", "mtype", "meso"]
    chandelier = get_term("chandelier")
    assert chandelier.systems_for("subclass") == ["meso"]  # falls back
    l2 = get_term("l2_pyramidal")
    assert l2.systems_for("subclass") == ["mtype"]  # subclass -> mtype -> meso


@pytest.mark.parametrize("text", ["L1", "layer 1", "white matter", "L2/3"])
def test_layers_are_not_cell_types(text):
    with pytest.raises(UnknownTermError) as err:
        resolve(text)
    assert "is a layer" in str(err.value)


def test_error_label_is_not_a_type(cells):
    from microns_finder.data import known_labels

    assert "error" not in known_labels(cells.assign(cell_type="error"))["subclass"]


def test_always_required_systems():
    assert get_term("pv_basket").systems_for("subclass") == ["subclass", "meso"]
    assert get_term("martinotti").systems_for("subclass") == ["subclass", "meso"]
    assert get_term("basket").systems_for("subclass") == ["subclass"]
