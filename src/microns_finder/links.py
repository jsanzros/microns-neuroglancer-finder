"""Build Neuroglancer (Spelunker) links for selected cells with nglui."""

from __future__ import annotations

import warnings

import pandas as pd

from . import config
from .query import proofreading_summary

# Colour-blind-friendly categorical palette (Okabe-Ito + extras).
PALETTE = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#999999", "#882255", "#44AA99"]


def cell_label(row) -> str:
    """One-line description shown in Neuroglancer next to each cell."""
    types = [t for t in (row.cell_type, row.mtype, row.meso_type) if isinstance(t, str)]
    kind = " / ".join(dict.fromkeys(types)) or (row.broad_type if isinstance(row.broad_type, str) else "unlabeled")
    parts = [kind, f"{row.layer} {row.depth_um:.0f} µm", row.visual_area if isinstance(row.visual_area, str) else "area ?"]
    proof = proofreading_summary(row)
    if proof != "none":
        parts.append(f"proofread: {proof}")
    if isinstance(row.coregistered, str):
        parts.append(f"functional: {row.coregistered}")
    parts.append(f"nucleus {row.nucleus_id}")
    return " | ".join(parts)


def _colors(cells: pd.DataFrame, color_by: str) -> dict[int, str]:
    if color_by == "type":
        keys = cells.cell_type.fillna(cells.broad_type).fillna("unlabeled")
        lookup = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(dict.fromkeys(keys))}
        return {int(r): lookup[k] for r, k in zip(cells.root_id, keys)}
    return {int(r): PALETTE[i % len(PALETTE)] for i, r in enumerate(cells.root_id)}


def build_state(
    cells: pd.DataFrame,
    client=None,
    *,
    title: str | None = None,
    synapses: bool = False,
    max_synapse_cells: int = 3,
    color_by: str | None = None,
    segment_properties: bool = True,
    info: dict | None = None,
):
    """Return an nglui ViewerState showing `cells` (rows of the cell table).

    If `info` is a dict, it is filled with what was added (e.g. synapse counts).
    """
    from nglui.statebuilder import ViewerState

    if cells.empty:
        raise ValueError("No cells to show.")
    cells = cells.drop_duplicates("root_id").reset_index(drop=True)
    cells = cells.assign(label=[cell_label(r) for r in cells.itertuples()])
    color_by = color_by or ("cell" if len(cells) <= len(PALETTE) else "type")

    first = cells.iloc[0]
    position = [float(first.x), float(first.y), float(first.z)]
    if client is not None:
        vs = ViewerState(client=client, title=title, position=position, layout="xy-3d")
        vs.add_layers_from_client(client, segmentation="cells", alpha_3d=1.0)
    else:
        vs = ViewerState(dimensions=list(config.VOXEL_RESOLUTION), title=title, position=position, layout="xy-3d")
        vs.add_image_layer(config.IMAGE_SOURCE, name="imagery")
        vs.add_segmentation_layer(config.SEGMENTATION_SOURCE, name="cells")

    roots = [int(r) for r in cells.root_id]
    vs.add_segments(roots, segment_colors=_colors(cells, color_by), name="cells")
    vs.add_points(
        cells,
        name="somata",
        point_column=["x", "y", "z"],
        segment_column="root_id",
        description_column="label",
        data_resolution=list(config.VOXEL_RESOLUTION),
    )

    if segment_properties and client is not None:
        try:
            vs.get_layer("cells").add_segment_properties(cells, client=client, id_column="root_id", label_column="label")
        except Exception as err:  # property upload is a nicety; the link works without it
            warnings.warn(f"Could not upload segment labels: {err}")

    if synapses:
        if client is None:
            raise ValueError("Showing synapses needs a CAVEclient.")
        neurons = cells[cells.broad_type.isin(["excitatory", "inhibitory"]).fillna(False)].head(max_synapse_cells)
        if neurons.empty:
            warnings.warn("Synapses are only shown for neurons.")
        else:
            ids = [int(r) for r in neurons.root_id]
            kw = dict(desired_resolution=list(config.VOXEL_RESOLUTION), split_positions=True)
            inputs = client.materialize.synapse_query(post_ids=ids, **kw)
            outputs = client.materialize.synapse_query(pre_ids=ids, **kw)
            if info is not None:
                info["synapses"] = {"cells": [str(i) for i in ids], "inputs": len(inputs), "outputs": len(outputs)}
            for df, name, partner in ((inputs, "inputs", "pre_pt_root_id"), (outputs, "outputs", "post_pt_root_id")):
                if len(df):
                    vs.add_points(
                        df,
                        name=name,
                        point_column="ctr_pt_position",
                        segment_column=partner,
                        data_resolution=list(config.VOXEL_RESOLUTION),
                        set_position=False,  # keep the view on the soma
                    )
    vs.set_selected_layer("cells")
    vs.position = position  # set last: adding layers from the client resets it
    return vs


def make_link(cells: pd.DataFrame, client=None, *, shorten: bool = True, **kwargs) -> str:
    """Return a Neuroglancer URL for `cells`. Short links need a CAVEclient."""
    vs = build_state(cells, client, **kwargs)
    if kwargs.get("synapses") and not (shorten and client is not None):
        warnings.warn("A full URL with synapse layers can be megabytes long and may not open; use a short link.")
    if shorten and client is not None:
        try:
            return vs.to_url(client=client, shorten=True)
        except Exception as err:
            warnings.warn(f"Could not shorten the link ({err}); returning the full URL.")
    return vs.to_url(target_url=config.VIEWER_SITE)
