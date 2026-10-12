import numpy as np
import pytest

from microns_finder.layers import ABOVE_PIA, assign_layer, parse_layers


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("L1", ["L1"]),
        ("layer 1", ["L1"]),
        ("1", ["L1"]),
        ("I", ["L1"]),
        ("L2/3", ["L2", "L3"]),
        ("layer 2/3", ["L2", "L3"]),
        ("L23", ["L2", "L3"]),
        ("II/III", ["L2", "L3"]),
        ("layer IV", ["L4"]),
        ("L5", ["L5"]),
        ("L5-6", ["L5", "L6"]),
        ("L5,L6", ["L5", "L6"]),
        ("L6b", ["L6"]),
        ("white matter", ["WM"]),
        ("WM", ["WM"]),
        ("deep layers", ["L5", "L6"]),
        (["L1", "L4"], ["L1", "L4"]),
    ],
)
def test_parse_layers(spec, expected):
    assert parse_layers(spec) == expected


def test_parse_layers_empty_and_bad():
    assert parse_layers(None) is None
    assert parse_layers("") is None
    with pytest.raises(ValueError):
        parse_layers("layer 9")


def test_assign_layer_boundaries():
    depths = [-5, 0, 84.9, 85, 174.9, 175, 249.9, 250, 364.9, 365, 509.9, 510, 719.9, 720, 900, np.nan]
    expected = [ABOVE_PIA, "L1", "L1", "L2", "L2", "L3", "L3", "L4", "L4", "L5", "L5", "L6", "L6", "WM", "WM", None]
    assert list(assign_layer(depths)) == expected
