"""JSON-ready results shared by the command line (`--json`) and the MCP server."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import config
from .layers import LAYER_BOUNDS
from .query import proofreading_summary, split_request
from .vocab import UnknownTermError, load_terms

LINK_NOTE = "Opens in Spelunker, a Neuroglancer deployment; the first time, it asks you to sign in with Google."


def _value(v):
    if v is None or v is pd.NA:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 1)
    return v


def cell_records(cells: pd.DataFrame) -> list[dict]:
    """One dict per cell. Root IDs are strings: 18-digit integers overflow JSON numbers in many tools."""
    return [
        {
            "nucleus_id": int(row.nucleus_id),
            "root_id": str(int(row.root_id)),
            "subclass": _value(row.cell_type),
            "mtype": _value(row.mtype),
            "meso_type": _value(row.meso_type),
            "broad_type": _value(row.broad_type),
            "subclass_source": _value(row.cell_type_source),
            "expert_label": bool(row.expert_label),
            "layer": _value(row.layer),
            "depth_um": round(float(row.depth_um), 1),
            "visual_area": _value(row.visual_area),
            "proofreading": proofreading_summary(row),
            "coregistered": _value(row.coregistered),
            "position_vx": [int(row.x), int(row.y), int(row.z)],
        }
        for row in cells.itertuples()
    ]


def link_contents(link: str | None, info: dict) -> dict | None:
    if not link:
        return None
    layers = ["imagery", "cells (selected segments, labeled)", "somata (one point per soma, with labels)"]
    if info.get("synapses"):
        layers += ["inputs (synapses onto the cells)", "outputs (synapses made by the cells)"]
    return {"layers": layers, **info, "viewer_note": LINK_NOTE}


def _make_link(finder, cells_or_result, notes: list[str], *, shorten=True, synapses=False, offline=False):
    info: dict = {}
    link = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            link = finder.link(cells_or_result, shorten=shorten, synapses=synapses, offline=offline, info=info)
        except ValueError as err:  # e.g. synapses requested offline
            notes.append(f"No link: {err}")
    notes.extend(str(w.message) for w in caught)
    return link, info


def _ids(values) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (str, int)):
        values = str(values).replace(",", " ").split()
    return [int(v) for v in values]


def find(
    finder,
    request: str | None = None,
    *,
    layer=None,
    area=None,
    link: bool = True,
    shorten: bool = True,
    synapses: bool = False,
    offline: bool = False,
    **options,
) -> dict:
    """Run a request like "astrocyte in layer 1" and return a JSON-ready result.

    `options` are the keyword arguments of `microns_finder.query.find_cells`
    (proofread, labels, expert, functional, where, depth, exclude, n, seed,
    prefer_proofread, allow_merged). Errors come back as {"error", "suggestions"}.
    """

    def is_term(text: str) -> bool:
        try:
            finder.resolve(text)
            return True
        except ValueError:
            return False

    text = (request or "").strip()
    try:
        term_text, layers, areas = split_request(text, is_term) if text else ("", None, None)
        if options.get("exclude") is not None:
            options["exclude"] = _ids(options["exclude"])
        result = finder.find(term_text or None, layer=layer or layers, area=area or areas, **options)
    except (UnknownTermError, ValueError) as err:
        return {"error": str(err), "suggestions": getattr(err, "suggestions", [])}

    url, info = (None, {})
    if link and len(result.cells):
        url, info = _make_link(finder, result, result.notes, shorten=shorten, synapses=synapses, offline=offline)
    return {
        "datastack": config.DATASTACK,
        "version": finder.version,
        "request": text or None,
        "term": result.term.to_dict() if result.term else None,
        "params": {k: v for k, v in result.params.items()},
        "filters": result.filters,
        "pool_size": result.pool_size,
        "n_returned": len(result.cells),
        "cells": cell_records(result.cells),
        "notes": result.notes,
        "link": url,
        "link_contents": link_contents(url, info),
    }


def show(finder, ids, *, link: bool = True, synapses: bool = False, offline: bool = False) -> dict:
    """Describe cells given root or nucleus IDs, with a link."""
    wanted = _ids(ids)
    rows = finder.lookup(wanted)
    missing = sorted(set(wanted) - set(rows.root_id) - set(rows.nucleus_id))
    notes = []
    if missing:
        notes.append(f"not in the v{finder.version} cell table (an outdated root ID, or not a cell): {missing}")
    url, info = (None, {})
    if link and not rows.empty:
        url, info = _make_link(finder, rows, notes, synapses=synapses, offline=offline)
    return {
        "datastack": config.DATASTACK,
        "version": finder.version,
        "cells": cell_records(rows),
        "missing": [str(m) for m in missing],
        "notes": notes,
        "link": url,
        "link_contents": link_contents(url, info),
    }


def terms(finder=None, *, counts: bool = False, labels: str = "subclass") -> list[dict]:
    """The vocabulary, optionally with the number of matching cells per term."""
    from .query import find_cells

    out = []
    for term in load_terms():
        entry = term.to_dict()
        if counts and finder is not None:
            entry["cells"] = find_cells(finder.cells, term, labels=labels, n=0).pool_size
        out.append(entry)
    return out


def layers() -> dict:
    return {
        "unit": "µm below the pial surface (standard_transform space)",
        "layers": [
            {"layer": name, "top_um": top, "bottom_um": None if np.isinf(bottom) else bottom}
            for name, top, bottom in LAYER_BOUNDS
        ],
        "note": "Derived from the data (see microns_finder/layers.py). Treat somata within ~15 µm of a boundary as ambiguous.",
    }
