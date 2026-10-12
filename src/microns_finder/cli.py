"""Command-line interface: `microns-finder find astrocyte in layer 1`."""

from __future__ import annotations

import argparse
import json
import sys
import warnings

import numpy as np
import pandas as pd

from . import __version__, config


def _where(items: list[str] | None) -> dict | None:
    if not items:
        return None
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--where expects COLUMN=VALUE[,VALUE], got {item!r}")
        col, vals = item.split("=", 1)
        out[col.strip()] = [v.strip() for v in vals.split(",") if v.strip()]
    return out


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _depth(text: str | None):
    if not text:
        return None
    lo, _, hi = text.partition("-")
    return float(lo), float(hi)


def _ids(text: str | None) -> list[int] | None:
    if not text:
        return None
    return [int(t) for t in text.replace(",", " ").split()]


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), 1)
    if value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    return value


def _cell_records(cells: pd.DataFrame) -> list[dict]:
    from .query import proofreading_summary

    records = []
    for row in cells.itertuples():
        records.append(
            {
                "nucleus_id": int(row.nucleus_id),
                "root_id": str(int(row.root_id)),  # string: 18-digit IDs overflow JSON numbers in some tools
                "subclass": _jsonable(row.cell_type),
                "mtype": _jsonable(row.mtype),
                "meso_type": _jsonable(row.meso_type),
                "broad_type": _jsonable(row.broad_type),
                "subclass_source": _jsonable(row.cell_type_source),
                "expert_label": bool(row.expert_label),
                "layer": _jsonable(row.layer),
                "depth_um": round(float(row.depth_um), 1),
                "visual_area": _jsonable(row.visual_area),
                "proofreading": proofreading_summary(row),
                "coregistered": _jsonable(row.coregistered),
                "position_vx": [int(row.x), int(row.y), int(row.z)],
            }
        )
    return records


def _print_table(df: pd.DataFrame) -> None:
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 40):
        print(df.to_string(index=False))


def cmd_find(args) -> int:
    from .finder import Finder
    from .query import split_request
    from .vocab import UnknownTermError

    finder = Finder(version=args.version, refresh=args.refresh)

    def is_term(text: str) -> bool:
        try:
            finder.resolve(text)
            return True
        except ValueError:
            return False

    text = " ".join(args.request).strip()
    try:
        term_text, layers, areas = split_request(text, is_term) if text else ("", None, None)
        layer = args.layer or layers
        area = args.area or areas
        result = finder.find(
            term_text or None,
            layer=layer,
            area=area,
            proofread=args.proofread,
            labels=args.labels,
            expert=args.expert,
            functional=args.functional,
            where=_where(args.where),
            depth=_depth(args.depth),
            exclude=_ids(args.exclude),
            n=args.n,
            seed=args.seed,
            prefer_proofread=not args.random,
            allow_merged=args.allow_merged,
        )
    except (UnknownTermError, ValueError) as err:
        if args.json:
            print(json.dumps({"error": str(err), "suggestions": getattr(err, "suggestions", [])}))
        else:
            print(f"error: {err}", file=sys.stderr)
        return 2

    link, link_info = None, {}
    if not args.no_link and len(result.cells):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                link = finder.link(
                    result, shorten=not args.long_url, synapses=args.synapses, offline=args.offline, info=link_info
                )
            except ValueError as err:  # e.g. --synapses with --offline
                result.notes.append(f"No link: {err}")
        result.notes.extend(str(w.message) for w in caught)

    if args.json:
        payload = {
            "datastack": config.DATASTACK,
            "version": finder.version,
            "request": text or None,
            "term": result.term.to_dict() if result.term else None,
            "params": result.params,
            "filters": result.filters,
            "pool_size": result.pool_size,
            "n_returned": len(result.cells),
            "cells": _cell_records(result.cells),
            "notes": result.notes,
            "link": link,
            "link_contents": _link_contents(link, link_info),
        }
        print(json.dumps(payload, indent=2, default=_jsonable))
        return 0

    title = result.term.label if result.term else "cells"
    print(f"MICrONS {config.DATASTACK} v{finder.version}: {title}")
    for f in result.filters:
        print(f"  - {f}")
    print(f"{result.pool_size} matching cells, showing {len(result.cells)}")
    if len(result.cells):
        print()
        _print_table(result.summary_table())
    for note in result.notes:
        print(f"\nnote: {note}")
    if link_info.get("synapses"):
        syn = link_info["synapses"]
        print(f"\nsynapse layers: {syn['inputs']} inputs and {syn['outputs']} outputs of {len(syn['cells'])} cell(s)")
    if link:
        print(f"\nNeuroglancer: {link}\n{LINK_NOTE}")
    return 0


LINK_NOTE = "(Opens in Spelunker, a Neuroglancer deployment; the first time, it asks you to sign in with Google.)"


def _link_contents(link, info) -> dict | None:
    if not link:
        return None
    layers = ["imagery", "cells (selected segments, labeled)", "somata (one point per soma, with labels)"]
    if info.get("synapses"):
        layers += ["inputs (synapses onto the cells)", "outputs (synapses made by the cells)"]
    return {"layers": layers, **info, "viewer_note": LINK_NOTE}


def cmd_terms(args) -> int:
    from .vocab import LABEL_COLUMNS, load_terms

    terms = load_terms()
    counts = {}
    if args.counts:
        from .finder import Finder
        from .query import find_cells

        cells = Finder(version=args.version).cells
        counts = {t.key: find_cells(cells, t, labels=args.labels, n=0).pool_size for t in terms}
    if args.json:
        print(json.dumps([{**t.to_dict(), **({"cells": counts[t.key]} if counts else {})} for t in terms], indent=2))
        return 0
    group = None
    for t in terms:
        if t.group != group:
            group = t.group
            print(f"\n[{group}]")
        defs = "; ".join(f"{LABEL_COLUMNS[s]}={'/'.join(v)}" for s, v in t.definitions.items()) or "broad_type only"
        count = f"  ({counts[t.key]} cells)" if counts else ""
        print(f"  {t.key:16s} {t.label}{count}\n  {'':16s} {defs}\n  {'':16s} also: {', '.join(t.synonyms[:6])}")
    print("\nRaw label values (e.g. L2a, 6P-CT, AltBasket) are accepted too.")
    return 0


def cmd_show(args) -> int:
    from .finder import Finder

    finder = Finder(version=args.version)
    ids = _ids(" ".join(args.ids))
    rows = finder.lookup(ids)
    missing = sorted(set(ids) - set(rows.root_id) - set(rows.nucleus_id))
    notes = []
    if missing:
        notes.append(f"not in the v{finder.version} cell table (an outdated root ID, or not a cell): {missing}")
    link, info = None, {}
    if not rows.empty and not args.no_link:
        try:
            link = finder.link(rows, synapses=args.synapses, offline=args.offline, info=info)
        except ValueError as err:
            notes.append(f"No link: {err}")
    if args.json:
        payload = {
            "cells": _cell_records(rows),
            "missing": [str(m) for m in missing],
            "notes": notes,
            "link": link,
            "link_contents": _link_contents(link, info),
        }
        print(json.dumps(payload, indent=2))
        return 0 if not rows.empty else 2
    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    if rows.empty:
        return 2
    _print_table(rows.drop(columns=["xt_um", "zt_um"]).T.reset_index().rename(columns={"index": "field"}))
    if link:
        print(f"\nNeuroglancer: {link}\n{LINK_NOTE}")
    return 0


def cmd_layers(args) -> int:
    from .layers import LAYER_BOUNDS

    print("Soma depth below the pia (µm, standard_transform space):")
    for name, top, bottom in LAYER_BOUNDS:
        print(f"  {name:3s} {top:5.0f} - {'' if np.isinf(bottom) else f'{bottom:.0f}'}")
    return 0


def cmd_cache(args) -> int:
    from .data import cache_info, load_cells

    if args.refresh or cache_info(args.version) is None:
        load_cells(args.version, refresh=True)
    print(json.dumps(cache_info(args.version), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="microns-finder",
        description="Find MICrONS cells by type, layer and area, and open them in Neuroglancer.",
    )
    p.add_argument("--about", action="version", version=f"microns-finder {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--version", type=int, default=config.DEFAULT_VERSION, help=f"materialization version (default {config.DEFAULT_VERSION})")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    f = sub.add_parser("find", help="find cells, e.g. `find astrocyte in layer 1`")
    f.add_argument("request", nargs="*", help='cell type, optionally with "in layer X" / "in the white matter" / "in V1"')
    f.add_argument("--layer", help="L1, L2, L3, L2/3, L4, L5, L6, WM (comma-separate several)")
    f.add_argument("--area", help="V1, RL, AL, LM or HVA")
    f.add_argument("--proofread", choices=["any", "dendrite", "axon", "both", "full"], help="only proofread cells")
    f.add_argument("--labels", choices=["subclass", "mtype", "meso", "consensus"], default="subclass", help="label system (default subclass)")
    f.add_argument("--expert", action="store_true", help="only cells with expert (manual) subclass labels")
    f.add_argument("--functional", action="store_true", help="only cells coregistered with two-photon imaging")
    f.add_argument("--where", action="append", metavar="COL=VAL", help="extra filter on any cell-table column (repeatable)")
    f.add_argument("--depth", metavar="MIN-MAX", help="soma depth range in µm below the pia")
    f.add_argument("--exclude", metavar="IDS", help="root or nucleus IDs to skip (comma separated)")
    f.add_argument("-n", type=_positive, default=3, help="number of cells (default 3)")
    f.add_argument("--seed", type=int, default=0, help="change to get different cells")
    f.add_argument("--random", action="store_true", help="do not put proofread cells first")
    f.add_argument("--allow-merged", action="store_true", help="include segments containing several nuclei")
    f.add_argument("--synapses", action="store_true", help="add input and output synapse layers (neurons only)")
    f.add_argument("--no-link", action="store_true", help="do not build a Neuroglancer link")
    f.add_argument("--long-url", action="store_true", help="full URL instead of a short link")
    f.add_argument("--offline", action="store_true", help="build the link without contacting CAVE (long URL, no labels)")
    f.add_argument("--refresh", action="store_true", help="re-download the cell table")
    common(f)
    f.set_defaults(func=cmd_find)

    t = sub.add_parser("terms", help="list the cell-type vocabulary")
    t.add_argument("--counts", action="store_true", help="number of matching cells per term")
    t.add_argument("--labels", choices=["subclass", "mtype", "meso", "consensus"], default="subclass")
    common(t)
    t.set_defaults(func=cmd_terms)

    s = sub.add_parser("show", help="describe cells by root or nucleus ID and link them")
    s.add_argument("ids", nargs="+")
    s.add_argument("--synapses", action="store_true")
    s.add_argument("--no-link", action="store_true")
    s.add_argument("--offline", action="store_true")
    common(s)
    s.set_defaults(func=cmd_show)

    lay = sub.add_parser("layers", help="print the layer depth boundaries")
    lay.set_defaults(func=cmd_layers)

    c = sub.add_parser("cache", help="download or inspect the local cell table")
    c.add_argument("--refresh", action="store_true")
    c.add_argument("--version", type=int, default=config.DEFAULT_VERSION)
    c.set_defaults(func=cmd_cache)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
