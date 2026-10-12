"""Cortical layer assignment from soma depth.

Depth is the y coordinate (µm) after `standard_transform.minnie_ds`, which
rotates the volume so that y runs perpendicular to the pial surface and puts
the pia at y = 0.

MICrONS has no official layer-boundary table, so the boundaries below were
derived from the data at materialization v1926 with
``scripts/derive_layer_boundaries.py``. Each boundary is the depth that best
separates the somata of the excitatory classes on either side of it (fewest
cells on the wrong side). After the standard transform the L2-L6 boundaries
vary by only about ±10 µm across the volume (V1 to the higher visual areas);
L1/L2 varies by about ±12 µm and L6/WM by about ±25 µm (deeper on the HVA
side). One set of numbers is used everywhere, and queries rank somata within
15 µm of a requested layer's boundary last:

* L1 / L2      85 µm   neuronal density reaches half its L2 value
* L2 / L3     175 µm   L2a-c vs L3a-b excitatory m-types
* L3 / L4     250 µm   23P vs 4P
* L4 / L5     365 µm   4P vs 5P (IT, ET, NP)
* L5 / L6     510 µm   5P-IT vs 6P (IT, CT)
* L6 / WM     720 µm   below ~99% of 6P somata, where neuronal density collapses

Layer boundaries are approximate by nature; treat cells within ~15 µm of a
boundary as ambiguous.
"""

from __future__ import annotations

import re

import numpy as np

# (name, top, bottom) in µm below the pia; bottom is exclusive.
LAYER_BOUNDS: list[tuple[str, float, float]] = [
    ("L1", 0.0, 85.0),
    ("L2", 85.0, 175.0),
    ("L3", 175.0, 250.0),
    ("L4", 250.0, 365.0),
    ("L5", 365.0, 510.0),
    ("L6", 510.0, 720.0),
    ("WM", 720.0, np.inf),
]
LAYER_NAMES = [name for name, _, _ in LAYER_BOUNDS]
ABOVE_PIA = "pia"  # somata with negative depth (meninges, surface vessels)

_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
_ALIASES = {
    "wm": ["WM"],
    "white matter": ["WM"],
    "whitematter": ["WM"],
    "subcortical white matter": ["WM"],
    "23": ["L2", "L3"],
    "2/3": ["L2", "L3"],
    "2 3": ["L2", "L3"],
    "2-3": ["L2", "L3"],
    "upper": ["L1", "L2", "L3"],
    "superficial": ["L1", "L2", "L3"],
    "deep": ["L5", "L6"],
    "infragranular": ["L5", "L6"],
    "supragranular": ["L2", "L3"],
    "granular": ["L4"],
}


def assign_layer(depth_um) -> np.ndarray:
    """Return the layer name for each depth (µm below the pia)."""
    depth = np.asarray(depth_um, dtype=float)
    out = np.full(depth.shape, ABOVE_PIA, dtype=object)
    for name, top, bottom in LAYER_BOUNDS:
        out[(depth >= top) & (depth < bottom)] = name
    out[np.isnan(depth)] = None
    return out


def _parse_one(token: str) -> list[str]:
    t = token.strip().lower()
    t = re.sub(r"^(cortical\s+)?(layers?|lamina|l)\s*", "", t).strip()
    t = re.sub(r"\s*\b(layers?|cortex)$", "", t).strip()
    if not t:
        raise ValueError(f"Could not understand layer {token!r}")
    if t in _ALIASES:
        return list(_ALIASES[t])
    # Roman numerals, e.g. "II/III", "IV", "VI"
    parts = re.split(r"\s*[/-]\s*|\s+", t)
    if all(p in _ROMAN for p in parts):
        t = "/".join(_ROMAN[p] for p in parts)
        if t in _ALIASES:
            return list(_ALIASES[t])
    if re.fullmatch(r"[1-6]", t):
        return [f"L{t}"]
    m = re.fullmatch(r"([1-6])[ab]?\s*(?:/|-|to)\s*l?([1-6])[ab]?", t)
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        return [f"L{i}" for i in range(lo, hi + 1)]
    # Sublayers such as "5a" or "6b" are not split here; map them to the layer.
    m = re.fullmatch(r"([1-6])\s*[ab]", t)
    if m:
        return [f"L{m.group(1)}"]
    raise ValueError(
        f"Could not understand layer {token!r}. Use e.g. L1, L2, L3, L2/3, L4, L5, L6, WM (white matter)."
    )


def parse_layers(spec) -> list[str] | None:
    """Parse a layer request such as "L2/3", "layer 5", "IV", "white matter" or "L5,L6".

    Returns a sorted list of layer names, or None when `spec` is empty.
    """
    if spec is None:
        return None
    tokens = spec if isinstance(spec, (list, tuple)) else re.split(r"\s*(?:,|\+|&|\band\b|\bor\b)\s*", str(spec))
    layers: set[str] = set()
    for token in tokens:
        if str(token).strip():
            layers.update(_parse_one(str(token)))
    if not layers:
        return None
    return [name for name in LAYER_NAMES if name in layers]


def _best_split(upper: np.ndarray, lower: np.ndarray, step: float = 1.0) -> float:
    """Depth with the fewest `upper` cells below it plus `lower` cells above it."""
    upper, lower = np.sort(upper), np.sort(lower)
    cands = np.arange(min(upper.min(), lower.min()), max(upper.max(), lower.max()), step)
    errors = (len(upper) - np.searchsorted(upper, cands, side="right")) + np.searchsorted(lower, cands, side="left")
    return float(cands[int(np.argmin(errors))])


def derive_boundaries(cells) -> dict[str, float]:
    """Re-derive the layer boundaries from a cell table (see the module docstring)."""
    ok = (cells.nuclei_in_segment == 1) & (cells.broad_type == "excitatory").fillna(False)
    exc = cells[ok]
    depth = lambda mask: exc.loc[mask.fillna(False), "depth_um"].to_numpy()  # noqa: E731
    ct, mt = exc.cell_type, exc.mtype

    neurons = cells[(cells.nuclei_in_segment == 1) & cells.broad_type.isin(["excitatory", "inhibitory"]).fillna(False)]
    hist, edges = np.histogram(neurons.depth_um, bins=np.arange(0, 200, 5))
    plateau = np.median(hist[(edges[:-1] >= 100) & (edges[:-1] < 150)])
    l1 = float(edges[np.argmax(hist >= plateau / 2)])

    return {
        "L1/L2": l1,
        "L2/L3": _best_split(depth(mt.isin(["L2a", "L2b", "L2c"])), depth(mt.isin(["L3a", "L3b"]))),
        "L3/L4": _best_split(depth(ct == "23P"), depth(ct == "4P")),
        "L4/L5": _best_split(depth(ct == "4P"), depth(ct.isin(["5P-IT", "5P-ET", "5P-NP"]))),
        "L5/L6": _best_split(depth(ct == "5P-IT"), depth(ct.isin(["6P-IT", "6P-CT"]))),
        "L6/WM": float(np.percentile(depth(ct.isin(["6P-IT", "6P-CT"])), 99)),
    }


def current_boundaries() -> dict[str, float]:
    names = LAYER_NAMES
    return {f"{a}/{b}": LAYER_BOUNDS[i][2] for i, (a, b) in enumerate(zip(names, names[1:]))}


def describe_layers(layers: list[str]) -> str:
    """Human-readable depth range for a set of layers, e.g. 'L2, L3 (85-250 µm)'."""
    bounds = [(top, bottom) for name, top, bottom in LAYER_BOUNDS if name in layers]
    top = min(b[0] for b in bounds)
    bottom = max(b[1] for b in bounds)
    depth = f">{top:.0f} µm" if np.isinf(bottom) else f"{top:.0f}-{bottom:.0f} µm"
    return f"{', '.join(layers)} ({depth} below pia)"
