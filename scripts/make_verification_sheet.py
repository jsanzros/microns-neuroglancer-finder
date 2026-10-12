"""Write docs/verification.md: one Neuroglancer link per vocabulary term, for a human to check.

Usage: python scripts/make_verification_sheet.py [--version 1926] [-n 3]

Open each link, look at the cells, and mark the row OK or not. Wrong rows
point at vocabulary entries (src/microns_finder/vocab.yaml) to fix.
"""

import argparse
import sys
from pathlib import Path

from microns_finder import Finder, config
from microns_finder.vocab import load_terms

EXAMPLES = [
    ("oligodendrocyte", "L2"),
    ("astrocyte", "WM"),
    ("astrocyte", "L1"),
    ("neurogliaform", None),
    ("basket", None),
    ("pyramidal", "L2"),
]


def row(finder, term, layer, n, labels="subclass"):
    res = finder.find(term, layer=layer, n=n, labels=labels)
    if res.cells.empty:
        return f"| {term} | {layer or ''} | {labels} | 0 | - | - | |"
    url = finder.link(res)
    ids = ", ".join(str(i) for i in res.cells.nucleus_id)
    request = res.term.label + (f" in {layer}" if layer else "")
    return f"| {request} | `{res.term.describe(labels)}` | {labels} | {res.pool_size} | [open]({url}) | {ids} | |"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", type=int, default=config.DEFAULT_VERSION)
    p.add_argument("-n", type=int, default=3)
    p.add_argument("--out", default="docs/verification.md")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    finder = Finder(version=args.version)

    header = "| Request | Definition | Labels | Pool | Link | Nucleus IDs | OK? |\n| --- | --- | --- | ---: | --- | --- | --- |"
    lines = [
        f"# Verification sheet (MICrONS v{args.version})",
        "",
        "Open each link and check that the cells look like the requested type (and sit in the requested layer).",
        "Write OK, or what looks wrong, in the last column. Cells are listed as nucleus IDs (stable across versions).",
        "Each link shows the requested cells plus a `somata` annotation layer whose descriptions give labels, depth and proofreading.",
        "",
        "## Example requests",
        "",
        header,
    ]
    for term, layer in EXAMPLES:
        lines.append(row(finder, term, layer, args.n))
        print("example", term, layer)
    lines += ["", "## Every vocabulary term (default labels)", "", header]
    for t in load_terms():
        lines.append(row(finder, t.key, None, args.n))
        print("term", t.key)
    lines += ["", "## Consensus examples (all label systems agree)", "", header]
    for t in load_terms():
        if len(t.definitions) > 1:
            lines.append(row(finder, t.key, None, args.n, labels="consensus"))
            print("consensus", t.key)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
