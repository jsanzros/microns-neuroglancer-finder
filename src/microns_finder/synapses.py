"""Find synapses between two kinds of cells, e.g. neurogliaform cells onto Martinotti cells.

Both kinds are selected with `find_cells`, the synapse table is queried for
synapses from one set onto the other, and the connected pairs are ranked:

1. pairs whose two cells every label system agrees on (as in `find_cells`);
2. pairs whose presynaptic axon is proofread (an unproofread axon can carry
   merged-in pieces of other cells, and with them synapses that aren't its own);
3. pairs with more synapses;
4. pairs whose postsynaptic dendrite is proofread;
5. the order `find_cells` gives each side (ending in a seeded shuffle).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config
from .query import _EXTENDED_AXON, FindResult, definitions_agree, find_cells, label_consistency

# Cells searched per side at most, each side's best first (labels agreeing,
# then proofread).
MAX_CELLS = 2000

# The search widens through these numbers of cells per side, then MAX_CELLS,
# and stops once it has enough pairs. The server is slow the first time it
# reads a cell's synapses, so starting small keeps most requests quick.
SEARCH_STEPS = (100, 500)

# Rows asked of the synapse table. Reaching it means some synapses were left out.
SYNAPSE_LIMIT = 100_000

SYNAPSE_COLUMNS = ["id", "size", "pre_pt_root_id", "post_pt_root_id", "ctr_pt_position_x", "ctr_pt_position_y", "ctr_pt_position_z"]


def axon_tier(cells: pd.DataFrame) -> pd.Series:
    """2 for a proofread, fully extended (or interareal) axon, 1 for another proofread axon, else 0."""
    extended = cells.axon_strategy.isin(_EXTENDED_AXON).fillna(False)
    return (cells.axon_cleaned.astype(int) + (cells.axon_cleaned & extended).astype(int)).astype(int)


@dataclass
class Connection:
    """A presynaptic cell, a postsynaptic cell and the synapses between them."""

    cells: pd.DataFrame  # two cell-table rows: presynaptic, then postsynaptic
    synapses: pd.DataFrame  # SYNAPSE_COLUMNS (positions in voxels), largest synapse first

    @property
    def pre(self) -> pd.Series:
        return self.cells.iloc[0]

    @property
    def post(self) -> pd.Series:
        return self.cells.iloc[1]


@dataclass
class SynapseResult:
    connections: list[Connection]
    pre: FindResult  # the presynaptic selection: term, filters, notes, pool size
    post: FindResult
    searched: dict  # cells searched per side, {"pre": n, "post": n}
    n_pairs: int  # connected pairs among the searched cells (with at least min_synapses)
    n_synapses: int  # synapses between the searched cells
    notes: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)


def _ranked(result: FindResult, tier: pd.Series) -> pd.DataFrame:
    """The cells of `result` (in find_cells order), those every label system agrees on first, then
    higher proofreading tiers. Keeps `_agree` and `_tier` for ranking pairs."""
    cells = result.cells
    agree = definitions_agree(cells, result.term) & label_consistency(cells)
    ordered = cells.assign(_agree=agree.astype(int).to_numpy(), _tier=tier.to_numpy())
    return ordered.sort_values(["_agree", "_tier"], ascending=False, kind="stable").reset_index(drop=True)


def _query(client, pre_cells: pd.DataFrame, post_cells: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Synapses from `pre_cells` onto `post_cells`, and whether the row limit cut them short."""
    syn = client.materialize.synapse_query(
        pre_ids=[int(r) for r in pre_cells.root_id],
        post_ids=[int(r) for r in post_cells.root_id],
        desired_resolution=list(config.VOXEL_RESOLUTION),
        split_positions=True,
        remove_autapses=False,  # done here, without caveclient's pandas warning
        limit=SYNAPSE_LIMIT,
    )
    return syn.loc[syn.pre_pt_root_id != syn.post_pt_root_id, SYNAPSE_COLUMNS], len(syn) >= SYNAPSE_LIMIT


def _rank_pairs(syn: pd.DataFrame, pre_cells: pd.DataFrame, post_cells: pd.DataFrame, min_synapses: int) -> pd.DataFrame:
    """Connected pairs with at least `min_synapses` synapses, best first (see the module docstring)."""
    pairs = syn.groupby(["pre_pt_root_id", "post_pt_root_id"]).size().rename("n_synapses").reset_index()
    pairs = pairs[pairs.n_synapses >= min_synapses]
    pre_info = pre_cells.assign(_rank=range(len(pre_cells))).set_index("root_id")
    post_info = post_cells.assign(_rank=range(len(post_cells))).set_index("root_id")
    return pairs.assign(
        agree=pairs.pre_pt_root_id.map(pre_info._agree) + pairs.post_pt_root_id.map(post_info._agree),
        pre_tier=pairs.pre_pt_root_id.map(pre_info._tier),
        post_tier=pairs.post_pt_root_id.map(post_info._tier),
        pre_rank=pairs.pre_pt_root_id.map(pre_info._rank),
        post_rank=pairs.post_pt_root_id.map(post_info._rank),
    ).sort_values(
        ["agree", "pre_tier", "n_synapses", "post_tier", "pre_rank", "post_rank"],
        ascending=[False, False, False, False, True, True],
    )


def _label(result: FindResult) -> str:
    return result.term.label if result.term is not None else "cell"


def find_synapses(
    client,
    cells: pd.DataFrame,
    pre=None,
    post=None,
    *,
    pre_layer=None,
    post_layer=None,
    pre_area=None,
    post_area=None,
    labels: str = "subclass",
    n: int = 1,
    min_synapses: int = 1,
    seed: int = 0,
    exclude=None,
    max_cells: int = MAX_CELLS,
) -> SynapseResult:
    """Return up to `n` pairs of cells connected by synapses, `pre` cells onto `post` cells.

    `pre` and `post` are cell types as `find_cells` takes them (None means any
    cell). Each side is searched best cells first: those every label system
    agrees on, then the best-proofread (axons on the presynaptic side, dendrites
    on the postsynaptic side). The search widens through SEARCH_STEPS cells per
    side, up to `max_cells`, until it finds `n` pairs.
    """
    if n < 0:
        raise ValueError("n must be 0 or more")
    if min_synapses < 1 or max_cells < 1:
        raise ValueError("min_synapses and max_cells must be 1 or more")
    common = dict(labels=labels, seed=seed, exclude=exclude, n=None)
    pre_res = find_cells(cells, pre, layer=pre_layer, area=pre_area, **common)
    post_res = find_cells(cells, post, layer=post_layer, area=post_area, **common)
    pre_name, post_name = _label(pre_res), _label(post_res)
    notes = [f"Presynaptic {pre_name}: {note}" for note in pre_res.notes]
    notes += [f"Postsynaptic {post_name}: {note}" for note in post_res.notes]
    params = {
        "pre": pre_res.params["term"],
        "pre_layer": pre_res.params["layer"],
        "pre_area": pre_res.params["area"],
        "post": post_res.params["term"],
        "post_layer": post_res.params["layer"],
        "post_area": post_res.params["area"],
        "labels": labels,
        "n": n,
        "min_synapses": min_synapses,
        "max_cells": max_cells,
        "seed": seed,
    }
    pre_ranked = _ranked(pre_res, axon_tier(pre_res.cells))
    post_ranked = _ranked(post_res, post_res.cells.dendrite_cleaned.astype(int))
    if pre_ranked.empty or post_ranked.empty:
        return SynapseResult([], pre_res, post_res, {"pre": 0, "post": 0}, 0, 0, notes, params)

    for limit in [s for s in SEARCH_STEPS if s < max_cells] + [max_cells]:
        pre_cells, post_cells = pre_ranked.head(limit), post_ranked.head(limit)
        syn, truncated = _query(client, pre_cells, post_cells)
        pairs = _rank_pairs(syn, pre_cells, post_cells, min_synapses)
        everyone = len(pre_cells) == len(pre_ranked) and len(post_cells) == len(post_ranked)
        if len(pairs) >= max(n, 1) or everyone:
            break

    partly = [
        f"the {len(kept):,} best of the {res.pool_size:,} {role} cells"
        for role, res, kept in (("presynaptic", pre_res, pre_cells), ("postsynaptic", post_res, post_cells))
        if res.pool_size > len(kept)
    ]
    if partly:
        notes.append(
            f"Searched {' and '.join(partly)} (labels agreeing first, then the best-proofread)"
            + (", which gave enough pairs." if limit < max_cells else "; raise the cell limit (--max-cells) to search more.")
        )
    if truncated:
        notes.append(
            f"The synapse query reached its limit of {SYNAPSE_LIMIT:,} synapses, so some pairs are missing; "
            "narrow the request with a layer or area."
        )

    connections = []
    for pair in pairs.head(n).itertuples():
        mine = syn[(syn.pre_pt_root_id == pair.pre_pt_root_id) & (syn.post_pt_root_id == pair.post_pt_root_id)]
        two = pd.concat(
            [pre_cells[pre_cells.root_id == pair.pre_pt_root_id], post_cells[post_cells.root_id == pair.post_pt_root_id]]
        )
        connections.append(
            Connection(
                cells=two.drop(columns=["_agree", "_tier"]).reset_index(drop=True),
                synapses=mine.sort_values(["size", "id"], ascending=[False, True]).reset_index(drop=True),
            )
        )

    unproofread = [str(c.pre.nucleus_id) for c in connections if axon_tier(c.cells.iloc[[0]]).iloc[0] == 0]
    if unproofread:
        notes.append(
            f"The presynaptic axon isn't proofread (nucleus {', '.join(unproofread)}), so a synapse may come from a "
            "piece of another cell merged into it; check each one in its zoom link."
        )
    if pairs.empty:
        at_least = f" with at least {min_synapses} synapses" if min_synapses > 1 else ""
        notes.append(
            f"No synapses from the searched {pre_name} cells onto the searched {post_name} cells{at_least}. "
            "Try another --labels system, drop a layer or area filter, or lower --min-synapses."
        )
    searched = {"pre": len(pre_cells), "post": len(post_cells)}
    return SynapseResult(connections, pre_res, post_res, searched, len(pairs), len(syn), notes, params)
