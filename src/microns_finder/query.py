"""Select cells from the cell table."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .layers import LAYER_BOUNDS, describe_layers, parse_layers
from .vocab import LABEL_COLUMNS, Term, resolve

# Somata closer than this to a requested layer's boundary are ranked last.
BOUNDARY_MARGIN_UM = 15.0

AREAS = ("V1", "RL", "AL", "LM")
_AREA_ALIASES = {
    "v1": ["V1"],
    "visp": ["V1"],
    "primary visual cortex": ["V1"],
    "primary visual": ["V1"],
    "rl": ["RL"],
    "visrl": ["RL"],
    "al": ["AL"],
    "visal": ["AL"],
    "lm": ["LM"],
    "visl": ["LM"],
    "hva": ["RL", "AL", "LM"],
    "hvas": ["RL", "AL", "LM"],
    "higher visual area": ["RL", "AL", "LM"],
    "higher visual areas": ["RL", "AL", "LM"],
}
PROOFREAD_MODES = ("any", "dendrite", "axon", "both", "full")
_EXTENDED_AXON = ("fully_extended", "interareal")


def parse_areas(spec) -> list[str] | None:
    if spec is None:
        return None
    tokens = spec if isinstance(spec, (list, tuple)) else re.split(r"\s*(?:,|\+|\band\b|\bor\b)\s*", str(spec))
    areas: set[str] = set()
    for token in tokens:
        t = str(token).strip().lower()
        if not t:
            continue
        if t not in _AREA_ALIASES:
            raise ValueError(f"Unknown visual area {token!r}. Use V1, RL, AL, LM or HVA (= RL, AL, LM).")
        areas.update(_AREA_ALIASES[t])
    return [a for a in AREAS if a in areas] or None


_PREP = r"(?:in|from|within|inside|of|at)"
_NUM = r"(?:[1-6][ab]?|iv|vi|v|i{1,3})"
_LAYER_LIST = rf"(?:l|layers?\s*){_NUM}(?:\s*(?:/|-|,|&|\band\b|\bor\b|\bto\b)\s*(?:l|layers?\s*)?{_NUM})*"
_LAYER_WORDS = r"white\s+matter|wm|(?:upper|superficial|deep|infragranular|supragranular)\s+layers?"
_LAYER = rf"(?:{_LAYER_WORDS}|{_LAYER_LIST})(?![\w/])"
_LAYER_PHRASE = re.compile(rf"\b{_PREP}\s+(?:the\s+)?(?:cortical\s+)?({_LAYER})", re.IGNORECASE)
_LEADING_LAYER = re.compile(rf"^\s*(?:the\s+)?({_LAYER})\s+", re.IGNORECASE)
_TRAILING_LAYER = re.compile(rf"\s+({_LAYER})\s*$", re.IGNORECASE)
_AREA_PHRASE = re.compile(
    rf"\b{_PREP}\s+(?:the\s+)?(?:area\s+)?(v1|visp|rl|al|lm|hvas?|higher\s+visual\s+areas?|primary\s+visual\s+cortex)\b",
    re.IGNORECASE,
)


def _resolves(text: str) -> bool:
    try:
        resolve(text)
        return True
    except ValueError:
        return False


def split_request(text: str, is_term=_resolves) -> tuple[str, list[str] | None, list[str] | None]:
    """Pull the layer and area out of a short request.

    "astrocyte in the white matter" -> ("astrocyte", ["WM"], None)
    "basket cell in layers 2 and 3 of V1" -> ("basket cell", ["L2", "L3"], ["V1"])
    "L4 basket cell" -> ("basket cell", ["L4"], None)
    A bare leading or trailing layer is split off only when the rest is a known
    term, so type names that contain a layer ("L5 ET", "layer 5 IT") stay whole.
    """
    layers = areas = None
    m = _AREA_PHRASE.search(text)
    if m:
        areas = parse_areas(re.sub(r"\s+", " ", m.group(1)))
        text = text[: m.start()] + " " + text[m.end() :]
    m = _LAYER_PHRASE.search(text)
    if m:
        layers = parse_layers(m.group(1))
        text = text[: m.start()] + " " + text[m.end() :]
    text = re.sub(r"\s+", " ", text).strip()
    if layers is None and text and not is_term(text):
        for pattern in (_LEADING_LAYER, _TRAILING_LAYER):
            m = pattern.search(text)
            rest = (text[: m.start()] + " " + text[m.end() :]).strip() if m else ""
            if rest and is_term(rest):
                layers, text = parse_layers(m.group(1)), rest
                break
    return text, layers, areas


def proofread_score(cells: pd.DataFrame) -> pd.Series:
    glia = cells.glia_proofreading.map({"non": 0, "clean": 1, "extended": 3}).fillna(0)
    neuron = (
        cells.dendrite_cleaned.astype(int)
        + cells.axon_cleaned.astype(int)
        + cells.axon_strategy.isin(_EXTENDED_AXON).fillna(False).astype(int)
    )
    return (glia + neuron).astype(int)


def proofreading_summary(row) -> str:
    if isinstance(row.glia_proofreading, str):
        return f"glia {row.glia_proofreading}"
    parts = []
    # A missing strategy is pd.NA, which can't be used with `or`.
    if row.dendrite_cleaned:
        parts.append(f"dendrite {row.dendrite_strategy if isinstance(row.dendrite_strategy, str) else 'clean'}")
    if row.axon_cleaned:
        parts.append(f"axon {row.axon_strategy if isinstance(row.axon_strategy, str) else 'clean'}")
    return ", ".join(parts) if parts else "none"


def _proofread_mask(cells: pd.DataFrame, mode: str) -> pd.Series:
    glia = cells.glia_proofreading.fillna("non")
    if mode == "any":
        return cells.dendrite_cleaned | cells.axon_cleaned | glia.isin(["clean", "extended"])
    if mode == "dendrite":
        return cells.dendrite_cleaned
    if mode == "axon":
        return cells.axon_cleaned
    if mode == "both":
        return cells.dendrite_cleaned & cells.axon_cleaned
    if mode == "full":
        axon_full = cells.axon_strategy.isin(_EXTENDED_AXON).fillna(False)
        return (cells.dendrite_cleaned & axon_full) | (glia == "extended")
    raise ValueError(f"proofread must be one of {PROOFREAD_MODES}, not {mode!r}")


# Subclass labels that fit each broad type. `broad_type` and `cell_type` come
# from different models for many cells, and sometimes contradict each other.
SUBCLASSES = {
    "excitatory": {"23P", "4P", "5P-IT", "5P-ET", "5P-NP", "6P-IT", "6P-CT", "6P-U", "WM-P"},
    "inhibitory": {"BC", "MC", "BPC", "NGC"},
    "nonneuron": {"astrocyte", "oligo", "OPC", "microglia", "pericyte"},
}


def label_consistency(cells: pd.DataFrame) -> pd.Series:
    """True where the subclass label fits the broad type (or either is missing)."""
    ok = cells.cell_type.isna() | cells.broad_type.isna()
    for broad, subclasses in SUBCLASSES.items():
        ok |= (cells.broad_type == broad).fillna(False) & cells.cell_type.isin(subclasses).fillna(False)
    return ok.astype(bool)


def _outer_edges(layers: list[str]) -> list[float]:
    """Boundaries of the depth range covered by `layers` (internal ones skipped)."""
    names = [name for name, _, _ in LAYER_BOUNDS]
    edges = []
    for i, (name, top, bottom) in enumerate(LAYER_BOUNDS):
        if name not in layers:
            continue
        if top > 0 and (i == 0 or names[i - 1] not in layers):
            edges.append(top)
        if np.isfinite(bottom) and (i + 1 == len(names) or names[i + 1] not in layers):
            edges.append(bottom)
    return edges


def definitions_agree(cells: pd.DataFrame, term: Term | None) -> pd.Series:
    """True where every label system that defines `term` gives the cell that term."""
    agree = pd.Series(True, index=cells.index)
    if term is not None:
        for system, values in term.definitions.items():
            agree &= cells[LABEL_COLUMNS[system]].isin(values).fillna(False)
    return agree.astype(bool)


def term_mask(cells: pd.DataFrame, term: Term, labels: str = "subclass") -> pd.Series:
    mask = pd.Series(True, index=cells.index)
    if term.broad_type:
        mask &= cells.broad_type.isin(term.broad_type).fillna(False)
    for system in term.systems_for(labels):
        mask &= cells[LABEL_COLUMNS[system]].isin(term.definitions[system]).fillna(False)
    return mask.astype(bool)


@dataclass
class FindResult:
    cells: pd.DataFrame
    pool_size: int
    term: Term | None
    filters: list[str]
    notes: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def summary_table(self) -> pd.DataFrame:
        df = self.cells
        return pd.DataFrame(
            {
                "nucleus_id": df.nucleus_id,
                "root_id": df.root_id,
                "subclass": df.cell_type,
                "mtype": df.mtype,
                "meso_type": df.meso_type,
                "layer": df.layer,
                "depth_um": df.depth_um.round(0).astype(int),
                "area": df.visual_area,
                "proofreading": [proofreading_summary(r) for r in df.itertuples()],
                "coregistered": df.coregistered,
            }
        ).reset_index(drop=True)


def find_cells(
    cells: pd.DataFrame,
    term: str | Term | None = None,
    *,
    layer=None,
    area=None,
    proofread: str | None = None,
    labels: str = "subclass",
    expert: bool = False,
    functional: bool = False,
    where: dict | None = None,
    depth: tuple[float, float] | None = None,
    exclude=None,
    n: int | None = 5,
    seed: int = 0,
    prefer_proofread: bool = True,
    allow_merged: bool = False,
) -> FindResult:
    """Return up to `n` cells matching the request (all of them, ranked, if `n` is None),
    plus the filters and caveats applied.

    Cells come only from the table; nothing is guessed. By default segments
    holding more than one nucleus (soma-soma merges) and nuclei without a
    segment are excluded, and proofread cells are returned first.
    """
    if n is not None and n < 0:
        raise ValueError("n must be 0 or more")
    filters: list[str] = []
    notes: list[str] = []
    if isinstance(term, str):
        from .data import known_labels

        term = resolve(term, known_labels(cells))
    if term is not None and term.layers:
        if layer is None:
            layer = list(term.layers)
        else:
            notes.append(f"'{term.label}' normally means somata in {', '.join(term.layers)}; used the requested layer instead.")
    consistent = label_consistency(cells)

    mask = pd.Series(True, index=cells.index)
    if allow_merged:
        mask &= cells.root_id != 0
        filters.append("has a segment")
    else:
        mask &= cells.nuclei_in_segment == 1
        filters.append("one nucleus per segment (no soma-soma merges)")

    if term is not None:
        mask &= term_mask(cells, term, labels)
        filters.append(f"{term.label}: {term.describe(labels)}")
        if labels == "consensus" and term.broad_type:
            mask &= consistent
            filters.append("subclass label consistent with broad type")
        used = term.systems_for(labels)
        if labels != "consensus" and used and used[0] != labels:
            notes.append(f"'{term.label}' has no {LABEL_COLUMNS[labels]} definition; used {LABEL_COLUMNS[used[0]]}.")
        if term.notes:
            notes.append(term.notes)

    layers = parse_layers(layer) if layer is not None else None
    if layers:
        mask &= cells.layer.isin(layers).fillna(False)
        filters.append(f"soma in {describe_layers(layers)}")
    areas = parse_areas(area) if area is not None else None
    if areas:
        mask &= cells.visual_area.isin(areas).fillna(False)
        filters.append(f"visual area in {areas}")
    if depth is not None:
        lo, hi = depth
        mask &= cells.depth_um.between(lo, hi)
        filters.append(f"soma depth {lo:g}-{hi:g} µm")
    if proofread:
        mask &= _proofread_mask(cells, proofread)
        filters.append(f"proofread: {proofread}")
        if proofread != "any" and term is not None and term.group == "nonneuronal":
            statuses = cells.glia_proofreading.value_counts().to_dict()
            notes.append(
                f"Glia are proofread as whole cells (VORTEX astrocyte/microglia tables, statuses {statuses}); "
                "use --proofread any."
            )
    if expert:
        mask &= cells.expert_label
        filters.append("expert (manual) subclass label")
    if functional:
        mask &= cells.coregistered.notna()
        filters.append("coregistered with two-photon functional imaging")
    for column, values in (where or {}).items():
        if column not in cells.columns:
            raise ValueError(f"Unknown column {column!r}. Columns: {', '.join(cells.columns)}")
        values = values if isinstance(values, (list, tuple, set)) else [values]
        if pd.api.types.is_bool_dtype(cells[column]):
            values = [str(v).lower() in ("1", "true", "yes") for v in values]
            mask &= cells[column].isin(values)
        elif pd.api.types.is_numeric_dtype(cells[column]):
            mask &= cells[column].isin([float(v) for v in values])
        else:
            mask &= cells[column].isin([str(v) for v in values]).fillna(False)
        filters.append(f"{column} in {list(values)}")
    if exclude:
        ids = {int(i) for i in exclude}
        mask &= ~(cells.root_id.isin(ids) | cells.nucleus_id.isin(ids))
        filters.append(f"excluding {len(ids)} cell(s) already shown")

    pool = cells[mask.astype(bool)]
    pool_size = len(pool)

    # Cells that every label system defined for the term agrees on, and whose
    # subclass doesn't contradict their broad type.
    defs_agree = definitions_agree(pool, term)
    pool_consistent = consistent.loc[pool.index]
    agree = defs_agree & pool_consistent
    if term is not None and term.broad_type and labels != "consensus" and pool_size:
        bad = 1 - pool_consistent.mean()
        if bad >= 0.05:
            notes.append(
                f"{bad:.0%} of these cells have a subclass label that contradicts their broad type "
                "(the two come from different models); they are ranked last, and --labels consensus drops them."
            )
    if term is not None and labels != "consensus" and len(term.definitions) > 1 and pool_size:
        others = [s for s in term.definitions if s not in term.systems_for(labels)]
        frac = defs_agree.mean()
        if frac < 0.9:
            names = " and ".join(LABEL_COLUMNS[s] for s in others)
            notes.append(
                f"Only {frac:.0%} of these {pool_size} cells are also '{term.label}' by {names}; "
                "use --labels consensus for cells all models agree on."
            )

    if layers and "WM" in layers:
        wm = cells[(cells.layer == "WM") & (cells.nuclei_in_segment == 1)]
        unlabeled = wm.broad_type.isna().mean() if len(wm) else 0
        notes.append(
            f"{unlabeled:.0%} of the {len(wm)} nuclei in the white matter have no cell-type label, "
            "so white-matter results come from the small labeled subset."
        )

    # Ranking: cells all label systems agree on first, then cells well inside
    # the requested layer, then (by default) proofread cells, then a seeded
    # shuffle so `seed` gives other examples.
    rng = np.random.default_rng(seed)
    order = pool.assign(_rand=rng.random(pool_size), _agree=agree.astype(int))
    keys, ascending = ["_agree"], [False]
    if layers:
        edges = _outer_edges(layers)
        if edges:
            dist = np.min(np.abs(pool.depth_um.to_numpy()[:, None] - np.array(edges)[None, :]), axis=1)
            order = order.assign(_clear=(dist >= BOUNDARY_MARGIN_UM).astype(int))
            keys, ascending = keys + ["_clear"], ascending + [False]
    if prefer_proofread:
        order = order.assign(_score=proofread_score(pool))
        keys, ascending = keys + ["_score"], ascending + [False]
    order = order.sort_values(keys + ["_rand"], ascending=ascending + [True])
    picked = order.drop(columns=[c for c in ("_rand", "_score", "_agree", "_clear") if c in order])
    if n is not None:
        picked = picked.head(n)

    if pool_size == 0:
        notes.append("No cells match. Try removing a filter (layer, area, proofreading) or another --labels system.")
    elif n is not None and pool_size < n:
        notes.append(f"Only {pool_size} cell(s) match.")

    params = {
        "term": term.key if term is not None else None,
        "layer": layers,
        "area": areas,
        "proofread": proofread,
        "labels": labels,
        "expert": expert,
        "functional": functional,
        "where": where or None,
        "depth": list(depth) if depth else None,
        "n": n,
        "seed": seed,
        "prefer_proofread": prefer_proofread,
    }
    return FindResult(cells=picked.reset_index(drop=True), pool_size=pool_size, term=term, filters=filters, notes=notes, params=params)
