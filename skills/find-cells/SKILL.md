---
name: find-cells
description: Find cells in the MICrONS mouse visual cortex electron-microscopy dataset (minnie65, the "cubic millimeter") by cell type, cortical layer, visual area and proofreading status, find pairs of cells connected by synapses, and return Neuroglancer (Spelunker) links to view them, including zoomed-in links to individual synapses. Use when the user asks to see, show, find or pick example cells or synapses in MICrONS, minnie65 or Neuroglancer, e.g. "show me an astrocyte in layer 1", "an oligodendrocyte in the white matter", "a basket cell with its synapses", "a proofread L5 ET cell in V1", "a neurogliaform cell with its synapses onto a Martinotti cell".
---

# Find MICrONS cells and open them in Neuroglancer

The `microns-finder` command does every lookup. **Never invent root IDs, nucleus IDs, coordinates or links**: report only what its output contains.

If the `microns-finder` MCP tools are connected (`find_cells`, `describe_cells`, `find_synapses`, `list_cell_types`, `layer_boundaries`), you can call them instead of the command line. They take the same options and return the same JSON, and everything below about presenting results still applies.

## Setup (once per machine)

1. Check it runs: `microns-finder --about`. If the command is missing and this skill came with the microns-finder plugin, install it from the plugin's folder:
   `pip install "${CLAUDE_PLUGIN_ROOT}"`, or run it without installing: `uvx --from "${CLAUDE_PLUGIN_ROOT}" microns-finder ...`. Otherwise: `pip install https://github.com/jsanzros/microns-neuroglancer-finder/archive/refs/heads/main.zip` (no git needed).
2. It needs a CAVE token for the public MICrONS data. If a command fails with an authentication or terms-of-service error, ask the user to run this in their own terminal, sign in with Google in the page that opens, accept the MICrONS terms, and paste the token into the second command:
   `python -c "from caveclient import CAVEclient; CAVEclient().auth.setup_token(make_new=True)"`
   `python -c "from caveclient import CAVEclient; CAVEclient().auth.save_token(token='PASTE_TOKEN_HERE')"`
   Don't ask for the token or handle it yourself.
3. The first query downloads the cell table (about 10 s). Later queries run offline from a local cache.

## Workflow

1. Turn each requested cell type into one `find` command (run several commands for a multi-part request) and always add `--json`:
   `microns-finder find <cell type> [--layer L] [--area A] [--proofread P] [--labels S] [-n N] [--synapses] --json`
   It returns 3 cells by default, which is good for comparing examples. Use `-n 1` when the user wants exactly one cell or asks for synapses. All 3 cells share one link.
2. Reply with the `link` first, then a compact table of the returned cells: nucleus ID, root ID, labels (subclass / mtype / meso_type), layer, depth (rounded), area, and proofreading summarized in a few words (e.g. "dendrite + full axon", "none"). Then pass on the `notes`. They carry the important caveats, such as label systems disagreeing or white matter being mostly unlabeled. Mention the materialization `version`, and once per conversation pass on `link_contents.viewer_note` (the viewer asks for a Google sign-in the first time). `link_contents.layers` lists what the link shows; with `--synapses`, `link_contents.synapses` gives the input and output counts.
3. For "another one" or "different examples", rerun with `--seed 1`, `--seed 2`, ... or `--exclude <IDs already shown>`.
4. If the output has an `error` with `suggestions`, pick the intended term or run `microns-finder terms` to see the vocabulary.
5. For synapses between two cell types, run `microns-finder synapses <PRE type> onto <POST type> [-n N] [--zoom K] [--labels S] --json`. Each side is written like a `find` request and can carry its own layer or area ("basket cell in layer 4 onto pyramidal in layer 4"). For each entry in `pairs`, reply with the `link` (both cells, every synapse marked), then each `zoom_links` entry as "synapse 1 (size …)", one link per synapse with the EM at full resolution. Then give a two-row table of `pre` and `post` and pass on the `notes`. Always say whether the presynaptic axon is proofread; a note warns when it isn't. For another pair, use `-n 2` or `--exclude` with the nucleus IDs already shown.

## Mapping requests to commands

| Request | Command |
| --- | --- |
| an astrocyte in layer 1 | `find astrocyte --layer L1` |
| an oligodendrocyte in the white matter | `find oligodendrocyte --layer WM` |
| a pyramidal cell in layer 2 (position) | `find pyramidal --layer L2` |
| interneurons in layers 2 and 3 | `find interneuron --layer L2,L3` |
| an L2 IT-type pyramidal cell (type) | `find "L2 IT"` |
| a neurogliaform cell all models agree on | `find neurogliaform --labels consensus` |
| a fully proofread L5 ET cell in V1, with synapses | `find "L5 ET" --area V1 --proofread full --synapses -n 1` |
| a chandelier cell | `find chandelier` |
| a PV basket cell / a CCK basket cell | `find "PV basket"` / `find "CCK basket"` |
| layer 1 interneurons | `find "L1 interneuron"` (applies L1 itself) |
| an L2/3 cell with two-photon functional data | `find "L2/3 pyramidal" --functional` |
| expert-labeled Martinotti cells in layer 5 | `find martinotti --layer L5 --expert` |
| L4c m-type cells | `find --where mtype=L4c` |
| tell me about / show cell 864691135... | `show 864691135... --json` |
| a neurogliaform cell with its synapses onto a Martinotti cell | `synapses neurogliaform onto martinotti` |
| two basket cells in L4 that synapse onto L4 excitatory cells, five synapses each | `synapses basket cell in layer 4 onto L4 excitatory -n 2 --zoom 5` |
| a chandelier cell's synapses onto a pyramidal cell, strongly connected | `synapses chandelier onto pyramidal --min-synapses 5` |

Rules of thumb:

- **Layer means soma position**, measured as depth below the pia: L1 0-85 µm, L2 85-175, L3 175-250, L4 250-365, L5 365-510, L6 510-720, WM over 720. `--layer` takes one layer or a comma-separated list ("L2,L3"; "L2/3" also works), and sublayers such as L6b map to their layer. Type names that contain a layer ("L5 ET", "L6 CT") are cell types, not positions. Combine a type with `--layer` only when the user asks for a position. A bare layer ("L1") is not a cell type; ask for a type in it ("neuron", "interneuron", "astrocyte"...).
- **Label systems** (`--labels`): `subclass` (default; the AIBS metamodel plus expert column labels), `mtype` (morphological types), `meso` (newer multifeature model), and `consensus` (all systems that define the term must agree). Use `consensus` when the user wants confident or typical examples, or when a note reports low agreement.
- Molecular names (PV, SST, VIP, CCK) are morphology-based proxies; EM has no molecular labels. Say so when you use them.
- Returned cells may sit in different layers unless you pass `--layer`; that is expected (e.g. neurogliaform cells occur in all layers).
- `--proofread`: `any`, `dendrite`, `axon`, `both`, or `full` (dendrite clean and axon fully extended). For glia use `any`: astrocytes and microglia have one whole-cell status, currently "clean" for all of them. Proofread cells are already ranked first by default, so add `--proofread` only when the user insists on proofread cells.
- `find ... --synapses` adds all input and output synapses of the shown cells (neurons only, first 3 cells). Keep `-n` between 1 and 5 for viewing. To see synapses between two particular types, use `synapses PRE onto POST` instead.
- `--where COLUMN=VALUE` filters any column of the cell table (see below), e.g. `--where meso_type=AltBasket`.

## Beyond the CLI

For requests the CLI can't express (cells near a coordinate, synaptic partners of a type, counts, plots), write Python against the library and still build links with it:

```python
from microns_finder import Finder
f = Finder()                      # version 1926 by default
cells = f.cells                   # pandas DataFrame, one row per nucleus
res = f.find("basket", layer="L4", n=3)
url = f.link(res)                 # or f.link(any_subset_of_cells) or f.link([root_or_nucleus_ids])
client = f.client                 # CAVEclient, e.g. client.materialize.synapse_query(pre_ids=[...])
```

Columns of `f.cells`: `nucleus_id`, `root_id`, `x y z` (voxels at 4×4×40 nm), `depth_um`, `layer`, `visual_area` (V1, RL, AL, LM), `broad_type` (excitatory, inhibitory, nonneuron), `cell_type` (subclass), `mtype`, `meso_type`, `*_source` (which table each label came from), `expert_label`, `dendrite_cleaned`, `axon_cleaned`, `dendrite_strategy`, `axon_strategy`, `glia_proofreading`, `coregistered` (manual, auto), `nuclei_in_segment` (more than 1 means a soma-soma merge), `nuc_volume`, `xt_um`, `zt_um`.

Root IDs change when cells are proofread, so nucleus IDs are the stable identifiers to quote. If the user publishes, point them to the citations in the README.
