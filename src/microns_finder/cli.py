"""Command-line interface: `microns-finder find astrocyte in layer 1`."""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import __version__, config, service


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


def _print_table(df: pd.DataFrame) -> None:
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 40):
        print(df.to_string(index=False))


def _print_link(payload: dict) -> None:
    contents = payload.get("link_contents") or {}
    if contents.get("synapses"):
        syn = contents["synapses"]
        print(f"\nsynapse layers: {syn['inputs']} inputs and {syn['outputs']} outputs of {len(syn['cells'])} cell(s)")
    if payload.get("link"):
        print(f"\nNeuroglancer: {payload['link']}\n({service.LINK_NOTE})")


def cmd_find(args) -> int:
    from .finder import Finder

    finder = Finder(version=args.version, refresh=args.refresh)
    payload = service.find(
        finder,
        " ".join(args.request),
        layer=args.layer,
        area=args.area,
        proofread=args.proofread,
        labels=args.labels,
        expert=args.expert,
        functional=args.functional,
        where=_where(args.where),
        depth=_depth(args.depth),
        exclude=args.exclude,
        n=args.n,
        seed=args.seed,
        prefer_proofread=not args.random,
        allow_merged=args.allow_merged,
        link=not args.no_link,
        shorten=not args.long_url,
        synapses=args.synapses,
        offline=args.offline,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
        return 2 if "error" in payload else 0
    if "error" in payload:
        print(f"error: {payload['error']}", file=sys.stderr)
        return 2

    title = payload["term"]["label"] if payload["term"] else "cells"
    print(f"MICrONS {payload['datastack']} v{payload['version']}: {title}")
    for f in payload["filters"]:
        print(f"  - {f}")
    print(f"{payload['pool_size']} matching cells, showing {payload['n_returned']}")
    if payload["cells"]:
        table = pd.DataFrame(payload["cells"]).drop(columns=["broad_type", "subclass_source", "expert_label", "position_vx"])
        table["depth_um"] = table.depth_um.round(0).astype(int)
        print()
        _print_table(table.rename(columns={"visual_area": "area"}))
    for note in payload["notes"]:
        print(f"\nnote: {note}")
    _print_link(payload)
    return 0


def cmd_terms(args) -> int:
    from .vocab import LABEL_COLUMNS, load_terms

    finder = None
    if args.counts:
        from .finder import Finder

        finder = Finder(version=args.version)
    entries = service.terms(finder, counts=args.counts, labels=args.labels)
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    group = None
    for term, entry in zip(load_terms(), entries):
        if term.group != group:
            group = term.group
            print(f"\n[{group}]")
        defs = "; ".join(f"{LABEL_COLUMNS[s]}={'/'.join(v)}" for s, v in term.definitions.items()) or "broad_type only"
        if term.layers:
            defs += f"; soma in {'/'.join(term.layers)}"
        count = f"  ({entry['cells']} cells)" if "cells" in entry else ""
        print(f"  {term.key:16s} {term.label}{count}\n  {'':16s} {defs}\n  {'':16s} also: {', '.join(term.synonyms[:6])}")
    print("\nRaw label values (e.g. L2a, 6P-CT, AltBasket) are accepted too.")
    return 0


def cmd_show(args) -> int:
    from .finder import Finder

    finder = Finder(version=args.version)
    payload = service.show(finder, " ".join(args.ids), link=not args.no_link, synapses=args.synapses, offline=args.offline)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload["cells"] else 2
    for note in payload["notes"]:
        print(f"note: {note}", file=sys.stderr)
    if not payload["cells"]:
        return 2
    table = pd.DataFrame(payload["cells"]).T.reset_index()
    table.columns = ["field"] + [f"cell {i + 1}" for i in range(len(payload["cells"]))]
    _print_table(table)
    _print_link(payload)
    return 0


def cmd_layers(args) -> int:
    info = service.layers()
    print(f"Soma depth, {info['unit']}:")
    for row in info["layers"]:
        bottom = "" if row["bottom_um"] is None else f"{row['bottom_um']:.0f}"
        print(f"  {row['layer']:3s} {row['top_um']:5.0f} - {bottom}")
    return 0


def cmd_cache(args) -> int:
    from .data import cache_info, load_cells

    if args.refresh or cache_info(args.version) is None:
        load_cells(args.version, refresh=True)
    print(json.dumps(cache_info(args.version), indent=2))
    return 0


def cmd_mcp_config(args) -> int:
    from .setup_helpers import mcp_config

    print(mcp_config(args.app))
    return 0


def cmd_install_skill(args) -> int:
    from .setup_helpers import install_skill

    agents = ("claude", "codex", "antigravity") if args.agent == "all" else (args.agent,)
    for path in install_skill(agents, dest=args.dest):
        print(f"installed {path}")
    print("Restart the agent (or start a new session) so it picks the skill up.")
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

    from .setup_helpers import CLIENTS

    m = sub.add_parser("mcp-config", help="show how to connect an AI app to the MCP server")
    m.add_argument("app", choices=CLIENTS)
    m.set_defaults(func=cmd_mcp_config)

    k = sub.add_parser("install-skill", help="copy the agent skill to where Claude Code, Codex or Antigravity read skills")
    k.add_argument("--agent", choices=["all", "claude", "codex", "antigravity"], default="all")
    k.add_argument("--dest", help="install into this skills folder instead")
    k.set_defaults(func=cmd_install_skill)

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
