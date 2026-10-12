import pandas as pd
import pytest

from microns_finder.data import COLUMNS


def _row(nucleus_id, root_id, depth, broad, cell_type=None, mtype=None, meso=None, **extra):
    row = {
        "nucleus_id": nucleus_id,
        "root_id": root_id,
        "x": 100000 + nucleus_id,
        "y": 100000,
        "z": 20000,
        "depth_um": float(depth),
        "layer": None,
        "visual_area": "V1",
        "broad_type": broad,
        "cell_type": cell_type,
        "mtype": mtype,
        "meso_type": meso,
        "broad_type_source": "aibs_metamodel_celltypes_v661",
        "cell_type_source": "aibs_metamodel_celltypes_v661" if cell_type else None,
        "mtype_source": None,
        "expert_label": False,
        "dendrite_cleaned": False,
        "axon_cleaned": False,
        "dendrite_strategy": None,
        "axon_strategy": None,
        "glia_proofreading": None,
        "coregistered": None,
        "nuclei_in_segment": 1,
        "nuc_volume": 250.0,
        "xt_um": 500.0,
        "zt_um": 800.0,
    }
    row.update(extra)
    return row


@pytest.fixture
def cells():
    from microns_finder.layers import assign_layer

    rows = [
        _row(1, 101, 40, "nonneuron", "astrocyte"),
        _row(2, 102, 60, "nonneuron", "astrocyte", glia_proofreading="extended"),
        _row(3, 103, 300, "nonneuron", "astrocyte"),
        _row(4, 104, 760, "nonneuron", "astrocyte"),
        _row(5, 105, 760, "nonneuron", "oligo"),
        _row(6, 106, 770, None),  # unlabeled white-matter nucleus
        _row(7, 107, 120, "excitatory", "23P", "L2a", "L2IT"),
        _row(8, 108, 200, "excitatory", "23P", "L3a", "L3IT", dendrite_cleaned=True, axon_cleaned=True, dendrite_strategy="extended", axon_strategy="fully_extended"),
        _row(9, 109, 60, "inhibitory", "NGC", "STC", "NGC"),
        _row(10, 110, 70, "inhibitory", "NGC", "DTC", "L1", dendrite_cleaned=True, axon_cleaned=True),
        _row(11, 111, 300, "inhibitory", "BC", "PTC", "PV", expert_label=True, cell_type_source="allen_v1_column_types_slanted_ref"),
        _row(12, 112, 420, "inhibitory", "BC", "PTC", "PV", visual_area="RL", coregistered="manual"),
        _row(13, 113, 450, "excitatory", "5P-ET", "L5ET", "L5ET", nuclei_in_segment=2),  # merged
        _row(14, 113, 455, "excitatory", "5P-ET", "L5ET", "L5ET", nuclei_in_segment=2),  # merged
        _row(15, 0, 450, "excitatory", "5P-ET", "L5ET", "L5ET", nuclei_in_segment=0),  # no segment
        _row(16, 116, -10, None),  # above the pia
        _row(17, 117, 120, "inhibitory", "23P", None, "L1"),  # broad type and subclass contradict
    ]
    df = pd.DataFrame(rows)
    df["layer"] = assign_layer(df.depth_um)
    for col in COLUMNS:
        if df[col].dtype == object:
            df[col] = df[col].astype("string")
    return df[COLUMNS]
