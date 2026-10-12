"""Re-derive the soma-depth layer boundaries from the MICrONS cell table.

Usage: python scripts/derive_layer_boundaries.py [--version 1926]

Prints the boundaries derived from the data next to the ones shipped in
microns_finder/layers.py, overall and in 150 µm bins across the volume
(V1 on the left, higher visual areas on the right), so you can see how much
they vary. Update LAYER_BOUNDS if a new release moves them.
"""

import argparse
import sys

import numpy as np

from microns_finder import config
from microns_finder.data import load_cells
from microns_finder.layers import current_boundaries, derive_boundaries


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", type=int, default=config.DEFAULT_VERSION)
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cells = load_cells(args.version)

    shipped = current_boundaries()
    overall = derive_boundaries(cells)
    bins = np.arange(150, 1700, 150)
    local = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        part = cells[(cells.xt_um >= lo) & (cells.xt_um < hi)]
        try:
            local.append(derive_boundaries(part))
        except ValueError:  # too few cells in an edge bin
            local.append(None)

    print(f"MICrONS v{args.version}: soma depth below the pia (µm)\n")
    print(f"{'boundary':9s} {'shipped':>8s} {'derived':>8s}   by x-bin (150 µm wide, V1 -> HVA)")
    for name in shipped:
        row = " ".join(f"{b[name]:5.0f}" if b else "    -" for b in local)
        print(f"{name:9s} {shipped[name]:8.0f} {overall[name]:8.0f}   {row}")


if __name__ == "__main__":
    main()
