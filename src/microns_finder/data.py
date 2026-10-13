"""Download, enrich and cache the MICrONS cell table.

One row per detected nucleus, built from the `aibs_cell_info` view (cell
types, m-types, proofreading, visual area) plus glia proofreading and
functional coregistration tables. The table is cached locally per
materialization version, so queries after the first are offline and instant.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, config
from .layers import assign_layer

GLIA_STATUS_RANK = {"non": 0, "clean": 1, "extended": 2}

# Bump when the cached table's columns or their meaning change.
CACHE_SCHEMA = 2

COLUMNS = [
    "nucleus_id",
    "root_id",
    "x",
    "y",
    "z",
    "depth_um",
    "layer",
    "visual_area",
    "broad_type",
    "cell_type",
    "mtype",
    "meso_type",
    "broad_type_source",
    "cell_type_source",
    "mtype_source",
    "expert_label",
    "dendrite_cleaned",
    "axon_cleaned",
    "dendrite_strategy",
    "axon_strategy",
    "glia_proofreading",
    "coregistered",
    "nuclei_in_segment",
    "nuc_volume",
    "xt_um",
    "zt_um",
]


def make_client(version: int = config.DEFAULT_VERSION):
    from caveclient import CAVEclient

    try:
        return CAVEclient(config.DATASTACK, version=version)
    except Exception as err:  # most often a missing or expired token
        raise RuntimeError(
            "Could not connect to the MICrONS CAVE server. If you have not set up a token yet, run:\n"
            "  python -c \"from caveclient import CAVEclient; CAVEclient().auth.setup_token(make_new=True)\"\n"
            "then save it with CAVEclient().auth.save_token(token='...').\n"
            f"Original error: {err}"
        ) from err


def _glia_status(client, table: str) -> pd.Series:
    df = client.materialize.query_table(table)
    df = df[df.pt_root_id != 0]
    rank = df.status.map(GLIA_STATUS_RANK).fillna(-1)
    best = df.assign(rank=rank).sort_values("rank").drop_duplicates("pt_root_id", keep="last")
    return best.set_index("pt_root_id").status


def build_cell_table(client) -> pd.DataFrame:
    """Query CAVE and return the enriched cell table (one row per nucleus)."""
    from standard_transform import minnie_ds

    raw = client.materialize.query_view(config.CELL_INFO_VIEW, split_positions=True)
    df = pd.DataFrame(
        {
            "nucleus_id": raw["id"].astype("int64"),
            "root_id": raw["pt_root_id"].astype("int64"),
            "x": raw["pt_position_x"].astype("int64"),
            "y": raw["pt_position_y"].astype("int64"),
            "z": raw["pt_position_z"].astype("int64"),
            "nuc_volume": raw["nuc_volume"].astype(float),
        }
    )
    for col in [
        "visual_area",
        "broad_type",
        "cell_type",
        "mtype",
        "meso_type",
        "broad_type_source",
        "cell_type_source",
        "mtype_source",
        "dendrite_strategy",
        "axon_strategy",
    ]:
        df[col] = raw[col].astype("string")
    df["dendrite_cleaned"] = raw["dendrite_cleaned"].fillna(False).astype(bool)
    df["axon_cleaned"] = raw["axon_cleaned"].fillna(False).astype(bool)
    df["expert_label"] = df.cell_type_source.isin(config.EXPERT_SOURCES).fillna(False).astype(bool)

    X = np.asarray(minnie_ds.transform("vx").apply(df[["x", "y", "z"]].to_numpy(dtype=float)))
    df["xt_um"], df["depth_um"], df["zt_um"] = X[:, 0], X[:, 1], X[:, 2]
    df["layer"] = pd.array(assign_layer(df.depth_um), dtype="string")

    counts = df.loc[df.root_id != 0, "root_id"].value_counts()
    df["nuclei_in_segment"] = df.root_id.map(counts).fillna(0).astype(int)

    glia = pd.concat(
        [_glia_status(client, config.ASTROCYTE_PROOFREADING_TABLE), _glia_status(client, config.MICROGLIA_PROOFREADING_TABLE)]
    )
    glia = glia[~glia.index.duplicated()]
    df["glia_proofreading"] = df.root_id.map(glia).astype("string")

    manual = set(client.materialize.query_table(config.COREG_MANUAL_TABLE).target_id)
    # A non-positive score means another nucleus fits the functional unit as well
    # or better (see the table description), so those automatic matches are skipped.
    auto_table = client.materialize.query_table(config.COREG_AUTO_TABLE)
    auto = set(auto_table.loc[auto_table.score > 0, "target_id"])
    coreg = np.where(df.nucleus_id.isin(manual), "manual", np.where(df.nucleus_id.isin(auto), "auto", None))
    df["coregistered"] = pd.array(coreg, dtype="string")

    return df[COLUMNS].reset_index(drop=True)


def _paths(version: int) -> tuple[Path, Path]:
    base = config.cache_dir() / f"cells_{config.DATASTACK}_v{version}_s{CACHE_SCHEMA}"
    return base.with_suffix(".parquet"), base.with_suffix(".json")


def snapshot_available(version: int = config.DEFAULT_VERSION) -> bool:
    return (version, CACHE_SCHEMA) in config.SNAPSHOTS


def download_snapshot(version: int = config.DEFAULT_VERSION) -> pd.DataFrame:
    """Download the prebuilt cell table for `version` (no CAVE token needed) into the cache."""
    if not snapshot_available(version):
        raise RuntimeError(
            f"There is no prebuilt cell table for v{version}; building one needs a CAVE token. "
            f"Prebuilt versions: {sorted(v for v, s in config.SNAPSHOTS if s == CACHE_SCHEMA)}."
        )
    url, sha256 = config.SNAPSHOTS[(version, CACHE_SCHEMA)]
    url = os.environ.get("MICRONS_FINDER_SNAPSHOT_URL", url)
    data_path, meta_path = _paths(version)
    tmp = data_path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, open(tmp, "wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if digest != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"The downloaded cell table is corrupted or changed (sha256 {digest}); try again.")
    tmp.replace(data_path)
    df = pd.read_parquet(data_path)
    _write_meta(meta_path, version, len(df), source="snapshot", snapshot_url=url)
    return df


def _write_meta(meta_path: Path, version: int, rows: int, **extra) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "datastack": config.DATASTACK,
                "version": version,
                "cache_schema": CACHE_SCHEMA,
                "rows": rows,
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "microns_finder_version": __version__,
                **extra,
            },
            indent=2,
        )
    )


def load_cells(version: int = config.DEFAULT_VERSION, refresh: bool = False, client=None, source: str = "auto") -> pd.DataFrame:
    """Return the cell table for `version`, downloading it on first use.

    `source`: "cave" builds it from the CAVE servers (needs a token); "snapshot"
    downloads the prebuilt copy attached to a GitHub release (no token); "auto"
    tries CAVE and falls back to the snapshot when no token works.
    """
    if source not in ("auto", "cave", "snapshot"):
        raise ValueError(f"source must be 'auto', 'cave' or 'snapshot', not {source!r}")
    data_path, meta_path = _paths(version)
    if data_path.exists() and not refresh:
        return pd.read_parquet(data_path)
    if source == "snapshot":
        return download_snapshot(version)
    try:
        client = client or make_client(version)
    except RuntimeError as err:
        if source != "auto":
            raise
        if snapshot_available(version):
            return download_snapshot(version)
        prebuilt = sorted(v for v, s in config.SNAPSHOTS if s == CACHE_SCHEMA)
        raise RuntimeError(
            f"{err}\n\nThere is no prebuilt cell table for v{version} (prebuilt: {prebuilt}), so this version needs a CAVE token."
        ) from err
    started = time.time()
    df = build_cell_table(client)
    df.to_parquet(data_path, index=False)
    _write_meta(meta_path, version, len(df), source="cave", build_seconds=round(time.time() - started, 1))
    return df


def cache_info(version: int = config.DEFAULT_VERSION) -> dict | None:
    data_path, meta_path = _paths(version)
    if not data_path.exists():
        return None
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {"path": str(data_path), **meta}


def known_labels(cells: pd.DataFrame) -> dict[str, set[str]]:
    """Label values present in the table, per label system ("error" is not a type)."""
    return {
        "subclass": set(cells.cell_type.dropna().unique()) - {"error"},
        "mtype": set(cells.mtype.dropna().unique()),
        "meso": set(cells.meso_type.dropna().unique()),
    }
