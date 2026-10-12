"""Dataset constants and cache location."""

from __future__ import annotations

import os
from pathlib import Path

DATASTACK = "minnie65_public"

# Latest public MICrONS release when this version of the package was made
# (September 2026). Public releases come out roughly every quarter; the
# vocabulary and layer boundaries were checked against this version.
DEFAULT_VERSION = 1926

# Voxel size (nm) of positions stored in the annotation tables.
VOXEL_RESOLUTION = (4, 4, 40)

# Used only when building links without a CAVEclient (e.g. in tests).
IMAGE_SOURCE = "precomputed://https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie/minnie65/em"
SEGMENTATION_SOURCE = "graphene://middleauth+https://minnie.microns-daf.com/segmentation/table/minnie65_public"
VIEWER_SITE = "https://spelunker.cave-explorer.org/"

CELL_INFO_VIEW = "aibs_cell_info"
ASTROCYTE_PROOFREADING_TABLE = "vortex_astrocyte_proofreading_status"
MICROGLIA_PROOFREADING_TABLE = "vortex_microglia_proofreading_status"
COREG_MANUAL_TABLE = "coregistration_manual_v4"
COREG_AUTO_TABLE = "coregistration_auto_phase3_fwd_apl_vess_combined_v2"

# Sources of the `subclass` label that are expert manual annotations rather
# than model predictions (the V1 column reference tables and manual corrections).
EXPERT_SOURCES = frozenset(
    {
        "allen_v1_column_types_slanted_ref",
        "aibs_column_nonneuronal_ref",
        "aibs_metamodel_celltypes_v661_corrections",
    }
)


def cache_dir() -> Path:
    """Where downloaded cell tables are stored (override with MICRONS_FINDER_CACHE)."""
    env = os.environ.get("MICRONS_FINDER_CACHE")
    path = Path(env) if env else Path.home() / ".cache" / "microns-finder"
    path.mkdir(parents=True, exist_ok=True)
    return path
