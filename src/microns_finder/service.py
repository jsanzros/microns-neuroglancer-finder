"""JSON-ready results shared by the command line (`--json`) and the MCP server."""

from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd

from . import config
from .layers import LAYER_BOUNDS
from .links import LinkWarning
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


def _with_link_notes(notes: list[str], make):
    """Return `make()`, passing the tool's own link caveats (LinkWarning) on as notes."""
    made = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", LinkWarning)
        try:
            made = make()
        except ValueError as err:  # e.g. synapses requested offline
            notes.append(f"No link: {err}")
    for w in caught:
        if issubclass(w.category, LinkWarning):
            notes.append(str(w.message))
        else:  # a library's warning (pandas, nglui...), not a caveat about the cells
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
    return made


def _make_link(finder, cells_or_result, notes: list[str], *, shorten=True, synapses=False, offline=False):
    info: dict = {}
    link = _with_link_notes(
        notes, lambda: finder.link(cells_or_result, shorten=shorten, synapses=synapses, offline=offline, info=info)
    )
    return link, info


def _term_checker(finder):
    def is_term(text: str) -> bool:
        try:
            finder.resolve(text)
            return True
        except ValueError:
            return False

    return is_term


def _ids(values) -> list[int]:
    """IDs from "1, 2", 1, or a list whose items may themselves be comma separated."""
    if values is None:
        return []
    if isinstance(values, (str, int)):
        values = [values]
    tokens = " ".join(str(v) for v in values).replace(",", " ").split()
    bad = [t for t in tokens if not t.isdecimal()]
    if bad:
        raise ValueError(f"Not a root or nucleus ID: {', '.join(bad)}. IDs are whole numbers, e.g. 864691135939998724 or 324332.")
    return [int(t) for t in tokens]


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
    text = (request or "").strip()
    try:
        term_text, layers, areas = split_request(text, _term_checker(finder)) if text else ("", None, None)
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
    """Describe cells given root or nucleus IDs, with a link. Bad IDs come back as {"error"}."""
    try:
        wanted = _ids(ids)
    except ValueError as err:
        return {"error": str(err)}
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


_ONTO = re.compile(r"\s+onto\s+|\s*(?:->|→)\s*", re.IGNORECASE)

SYNAPSE_LINK_CONTENTS = {
    "layers": [
        "imagery",
        "cells (presynaptic cell orange, postsynaptic cell blue, labeled)",
        "somata (one point per soma, with labels)",
        "synapses (one point per synapse between the two cells; the layer panel lists them, click one to jump to it)",
    ],
    "zoom_links": "Each opens on one synapse, largest first, with the EM at full resolution.",
    "viewer_note": LINK_NOTE,
}


def split_connection(text: str) -> tuple[str, str]:
    """ "neurogliaform onto martinotti" -> ("neurogliaform", "martinotti"). "->" and "→" work too."""
    parts = _ONTO.split(text.strip(), maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Write the request as PRE onto POST, e.g. 'neurogliaform onto martinotti', not {text!r}.")
    pre = re.sub(r"^(?:synapses\s+)?from\s+", "", parts[0].strip(), flags=re.IGNORECASE)
    return pre, parts[1].strip()


def synapse_records(synapses: pd.DataFrame) -> list[dict]:
    return [
        {
            "id": int(s.id),
            "size": int(s.size),
            "position_vx": [round(s.ctr_pt_position_x), round(s.ctr_pt_position_y), round(s.ctr_pt_position_z)],
        }
        for s in synapses.itertuples()
    ]


def _side(result, searched: int) -> dict:
    return {
        "term": result.term.to_dict() if result.term else None,
        "filters": result.filters,
        "pool_size": result.pool_size,
        "searched": searched,
    }


def synapses(
    finder,
    request: str | None = None,
    *,
    pre: str | None = None,
    post: str | None = None,
    area=None,
    zoom: int = 3,
    link: bool = True,
    shorten: bool = True,
    offline: bool = False,
    **options,
) -> dict:
    """Synapses between two cell types, as "neurogliaform onto martinotti" or as `pre` and `post`.

    Each side may name its own layer or area ("basket cell in layer 4"); `area`
    applies to a side that names none. `options` are the keyword arguments of
    `microns_finder.synapses.find_synapses` (labels, n, min_synapses, seed,
    exclude, max_cells). Errors come back as {"error", "suggestions"}.
    """
    is_term = _term_checker(finder)
    try:
        if request is not None and request.strip():
            pre, post = split_connection(request)
        sides = {}
        for role, text in (("pre", pre), ("post", post)):
            text = (text or "").strip()
            term_text, layers, areas = split_request(text, is_term) if text else ("", None, None)
            sides[role] = {"text": text or None, "term": term_text or None, "layer": layers, "area": areas or area}
        if options.get("exclude") is not None:
            options["exclude"] = _ids(options["exclude"])
        result = finder.synapses(
            sides["pre"]["term"],
            sides["post"]["term"],
            pre_layer=sides["pre"]["layer"],
            pre_area=sides["pre"]["area"],
            post_layer=sides["post"]["layer"],
            post_area=sides["post"]["area"],
            **options,
        )
    except (UnknownTermError, ValueError) as err:
        return {"error": str(err), "suggestions": getattr(err, "suggestions", [])}

    names = [res.term.label if res.term else "any cell" for res in (result.pre, result.post)]
    title = f"{names[0]} onto {names[1]} | MICrONS v{finder.version}"
    notes = result.notes
    pairs = []
    for conn in result.connections:
        made = None
        if link:
            made = _with_link_notes(
                notes,
                lambda conn=conn: finder.connection_links(conn, zoom=zoom, shorten=shorten, offline=offline, title=title),
            )
        overview, zooms = made or (None, [])
        pairs.append(
            {
                "pre": cell_records(conn.cells.iloc[[0]])[0],
                "post": cell_records(conn.cells.iloc[[1]])[0],
                "n_synapses": len(conn.synapses),
                "synapses": synapse_records(conn.synapses),
                "link": overview,
                "zoom_links": [
                    {"synapse_id": int(s.id), "size": int(s.size), "link": url}
                    for s, url in zip(conn.synapses.itertuples(), zooms)
                ],
            }
        )
    return {
        "datastack": config.DATASTACK,
        "version": finder.version,
        "request": {"pre": sides["pre"]["text"], "post": sides["post"]["text"]},
        "pre": _side(result.pre, result.searched["pre"]),
        "post": _side(result.post, result.searched["post"]),
        "params": result.params,
        "connected_pairs": result.n_pairs,
        "synapses_found": result.n_synapses,
        "n_returned": len(pairs),
        "pairs": pairs,
        "notes": notes,
        "link_contents": SYNAPSE_LINK_CONTENTS if any(p["link"] for p in pairs) else None,
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
