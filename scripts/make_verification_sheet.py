"""Write a verification sheet: Neuroglancer links for a human to check every vocabulary term.

The sheet is a working file for maintainers: it goes to local/ (git-ignored), not into the repository.

Usage: python scripts/make_verification_sheet.py [--version 1926] [-n 3]

Each row shows cells not shown in any earlier row, so every link adds new
examples. Classes with at most --all-below cells also get a link to every
cell. Consensus rows are listed only where consensus differs from the
default. Open each link, look at the cells, and note in the last column what
looks wrong; wrong rows point at vocabulary entries (src/microns_finder/vocab.yaml).
"""

import argparse
import sys
from pathlib import Path

from microns_finder import Finder, config
from microns_finder.query import find_cells
from microns_finder.vocab import LABEL_COLUMNS, load_terms

EXAMPLES = [
    ("oligodendrocyte", "L2"),
    ("astrocyte", "WM"),
    ("astrocyte", "L1"),
    ("neurogliaform", None),
    ("basket", None),
    ("pyramidal", "L2"),
]
SMALL_POOL = 50


class Sheet:
    def __init__(self, finder, n, all_below):
        self.finder, self.n, self.all_below = finder, n, all_below
        self.shown: set[int] = set()

    def row(self, term_key, layer=None, labels="subclass"):
        f = self.finder
        res = f.find(term_key, layer=layer, n=self.n, labels=labels, exclude=sorted(self.shown) or None)
        term = res.term
        systems = ", ".join(LABEL_COLUMNS[s] for s in term.systems_for(labels)) or "broad_type only"
        filters = "; ".join(x for x in res.filters if not x.startswith(("one nucleus", "excluding")))
        request = term.label + (f" in {layer}" if layer else "")
        notes = []
        # Pool size without the "already shown" exclusion, i.e. the real class size.
        pool = find_cells(f.cells, term, layer=layer, labels=labels, n=0).pool_size
        if pool < SMALL_POOL:
            notes.append(f"small class ({pool} cells)")
        if res.cells.empty:
            return f"| {request} | {labels} | {systems} | {filters} | {pool} | - | - | all {pool} shown in earlier rows | |"
        self.shown.update(int(i) for i in res.cells.nucleus_id)
        links = f"[{len(res.cells)} cells]({f.link(res)})"
        if pool <= self.all_below:
            everyone = f.find(term_key, layer=layer, n=pool, labels=labels)
            links += f" · [all {pool}]({f.link(everyone)})"
        ids = ", ".join(str(i) for i in res.cells.nucleus_id)
        return f"| {request} | {labels} | {systems} | `{filters}` | {pool} | {links} | {ids} | {'; '.join(notes)} | |"


HEADER = (
    "| Request | Mode | Label systems used | Filters | Pool | Links | Nucleus IDs | Notes | OK? |\n"
    "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |"
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", type=int, default=config.DEFAULT_VERSION)
    p.add_argument("-n", type=int, default=3)
    p.add_argument("--all-below", type=int, default=30, help="also link every cell of classes this small")
    p.add_argument("--out", default="local/verification.md")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sheet = Sheet(Finder(version=args.version), args.n, args.all_below)

    lines = [
        f"# Verification sheet (MICrONS v{args.version})",
        "",
        "Open each link and check that the cells look like the requested type and sit in the requested layer.",
        "Write OK, or what looks wrong, in the last column.",
        "",
        "- **Mode** is the `--labels` setting. **Label systems used** is what the mode resolves to for that term:"
        " a term may fall back to the only system that defines it (e.g. chandelier exists only in `meso_type`),"
        " or require a system in every mode (PV basket, Martinotti).",
        "- **Pool** is the number of matching cells (single-nucleus segments).",
        "- Every row shows cells that no earlier row showed. Classes of at most"
        f" {args.all_below} cells also get a link to all of them, since 3 examples say little about a small class.",
        "- Each link has a `somata` layer whose point descriptions give each cell's labels, depth and proofreading.",
        "- Cells are listed by nucleus ID (stable across releases).",
        "",
        "## Example requests",
        "",
        HEADER,
    ]
    for term, layer in EXAMPLES:
        lines.append(sheet.row(term, layer))
        print("example", term, layer)
    lines += ["", "## Every vocabulary term (default mode)", "", HEADER]
    for t in load_terms():
        lines.append(sheet.row(t.key))
        print("term", t.key)
    lines += ["", "## Consensus mode, where it differs from the default", "", HEADER]
    for t in load_terms():
        if t.systems_for("consensus") != t.systems_for("subclass"):
            lines.append(sheet.row(t.key, labels="consensus"))
            print("consensus", t.key)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
