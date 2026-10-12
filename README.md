# microns-finder

Ask for a cell type in plain language and get a Neuroglancer link to real examples in the [MICrONS](https://www.microns-explorer.org/cortical-mm3) cubic millimeter of mouse visual cortex.

```text
$ microns-finder find astrocyte in layer 1
MICrONS minnie65_public v1926: astrocyte
  - one nucleus per segment (no soma-soma merges)
  - astrocyte: broad_type in ['nonneuron'] AND cell_type in ['astrocyte']
  - soma in L1 (0-85 µm below pia)
785 matching cells, showing 3

 nucleus_id            root_id  subclass layer  depth_um area proofreading
     255123 864691136619043547 astrocyte    L1        52   V1   glia clean
     ...

Neuroglancer: https://spelunker.cave-explorer.org/#!middleauth+https://global.daf-apis.com/nglstate/api/v1/...
```

It works with any AI assistant, and without one:

- **Any MCP-capable AI**: ChatGPT, Gemini, Claude, Codex, GitHub Copilot, Cursor, Antigravity and others. The `microns-finder-mcp` server gives the AI four tools (`find_cells`, `describe_cells`, `list_cell_types`, `layer_boundaries`) through the open [Model Context Protocol](https://modelcontextprotocol.io). Ask "show me a neurogliaform cell everyone agrees on" or "a proofread L5 ET cell in V1 with its synapses". The AI turns the request into a query and the tool picks the cells, so cell IDs never come from the model.
- **Coding agents with a terminal**: an [Agent Skill](https://agentskills.io) ([`skills/find-cells/SKILL.md`](skills/find-cells/SKILL.md)) and [`AGENTS.md`](AGENTS.md) teach the agent to drive the command line.
- **The command line and Python**, with no AI at all.

Every answer states the filters that were applied, how many cells matched, and caveats such as "the label systems disagree on 71% of these cells". Each link opens Neuroglancer at the first cell, with all requested cells colored and each soma annotated with its labels, layer, depth and proofreading status.

## Install

```bash
pip install "git+https://github.com/jsanzros/microns-finder"
```

You need a free CAVE token for the public MICrONS data (Google sign-in, plus accepting the MICrONS terms of use):

```bash
python -c "from caveclient import CAVEclient; CAVEclient().auth.setup_token(make_new=True)"
python -c "from caveclient import CAVEclient; CAVEclient().auth.save_token(token='PASTE_TOKEN_HERE')"
```

Then download the cell table once (about 10 seconds): a table of the ~144,000 detected nuclei, saved to `~/.cache/microns-finder`. After that, queries run offline. Short links, segment labels and synapses still use the CAVE servers.

```bash
microns-finder cache
```

## Connect your AI

`microns-finder mcp-config <app>` prints the exact configuration for your machine, including the full path to the server, which desktop apps often need.

| AI | How it connects | Command |
| --- | --- | --- |
| Claude Desktop | local MCP server | `microns-finder mcp-config claude-desktop` |
| Claude Code | plugin (below) or local MCP server | `microns-finder mcp-config claude-code` |
| ChatGPT (web and desktop) | remote MCP server in Developer Mode (paid plans) | `microns-finder mcp-config chatgpt` |
| Codex (CLI, IDE, ChatGPT desktop) | local MCP server, plus the skill | `microns-finder mcp-config codex` |
| Gemini app (web) | remote MCP server under Connected Apps (some account types and regions) | `microns-finder mcp-config gemini-web` |
| Antigravity CLI (successor of Gemini CLI) | local MCP server, plus the skill | `microns-finder mcp-config antigravity` |
| Cursor | local MCP server | `microns-finder mcp-config cursor` |
| VS Code / GitHub Copilot | local MCP server | `microns-finder mcp-config vscode` |
| Any other MCP client | stdio command `microns-finder-mcp`, or the HTTP URL below | |

**Local apps** (desktop apps, coding agents) start the server themselves over stdio. Nothing else to run.

**Web apps** (ChatGPT, Gemini) only reach servers on the internet over HTTPS. Run the server in HTTP mode and give it a public address with a tunnel:

```bash
microns-finder-mcp --http --public --port 8000 --preload
cloudflared tunnel --url http://127.0.0.1:8000        # or your provider's tunnel; prints an https://... address
```

Add `https://<tunnel-address>/mcp` as a custom MCP connector/app with no authentication. `--public` lets the server answer requests addressed to the tunnel's domain; without it, only `localhost` is accepted (use `--allowed-host DOMAIN` to allow just one domain). While it runs, anyone with that URL can use the server. The data is public and read-only, but your CAVE token makes the short links, so don't share the URL and stop the tunnel when you're done. Menu names in ChatGPT and Gemini change between releases; see their help pages for the current path.

**Skills for coding agents.** `microns-finder install-skill` copies the skill to where Claude Code (`~/.claude/skills`), Codex (`~/.agents/skills`) and Antigravity (`~/.gemini/antigravity-cli/skills`) look for skills. Use `--agent codex` (or `claude`, `antigravity`) for just one, or `--dest DIR` for any other agent.

### As a Claude Code plugin

```text
/plugin marketplace add jsanzros/microns-finder
/plugin install microns-finder@microns-finder
```

The plugin installs the `find-cells` skill. It can also install the Python package from the plugin's own folder.

## Command line

```bash
microns-finder find oligodendrocyte in the white matter
microns-finder find pyramidal cell in layer 2
microns-finder find neurogliaform --labels consensus
microns-finder find "L5 ET" --area V1 --proofread full --synapses -n 1
microns-finder find martinotti --layer L5 --expert
microns-finder find "L2/3 pyramidal" --functional          # coregistered with two-photon imaging
microns-finder find --where mtype=L4c                      # raw label values work too
microns-finder find basket --seed 1                        # different examples
microns-finder show 864691135939998724                     # describe and link a cell by root or nucleus ID
microns-finder terms                                       # the vocabulary
microns-finder layers                                      # the layer boundaries
```

Add `--json` for machine-readable output: the same JSON the MCP tools return.

## Python

```python
from microns_finder import Finder

f = Finder()                                   # materialization v1926 by default
res = f.find("basket", layer="L2/3", n=3, labels="consensus")
res.summary_table()                            # pandas DataFrame
res.notes                                      # caveats
f.link(res, synapses=True)                     # short Neuroglancer link

f.cells                                        # the full table, one row per nucleus
f.link(f.cells.query("meso_type == 'ChC' and layer == 'L2'"))
```

## How cells are chosen

**Data.** One row per detected nucleus from the `aibs_cell_info` view of the public datastack `minnie65_public`, pinned to materialization **v1926** (September 2026). The view combines cell types, m-types, proofreading status and visual area. Added to it:
- soma depth and layer, from [standard_transform](https://github.com/CAVEconnectome/standard_transform),
- glia proofreading status, from the VORTEX astrocyte and microglia tables (all "clean" at v1926),
- functional coregistration: manual matches, plus automatic matches with a positive score (a non-positive score means another nucleus fits the functional unit as well or better).

**Exclusions.** Nuclei without a segment and segments containing more than one nucleus (soma-soma merges) are excluded unless you pass `--allow-merged`.

**Ranking.** Matching cells are ranked in this order, and the first `n` are returned:
1. cells that every label system defining the term agrees on;
2. cells at least 15 µm inside the requested layer, rather than near a boundary;
3. proofread cells (turn off with `--random`);
4. a seeded shuffle (`--seed`).

### Label systems

MICrONS has several cell-type classifications, and they disagree more than you might expect. `--labels` picks one:

| `--labels` | Column | Source |
| --- | --- | --- |
| `subclass` (default) | `cell_type` | AIBS soma/nucleus metamodel ([Elabbady et al. 2025](https://www.nature.com/articles/s41586-024-07765-7)), overridden by expert labels in the V1 column and manual corrections |
| `mtype` | `mtype` | m-types defined on the proofread V1 column ([Schneider-Mizell et al. 2025](https://doi.org/10.1038/s41586-024-07780-8)), predicted volume-wide by the same metamodel (`aibs_metamodel_mtypes_v661_v2`) |
| `meso` | `meso_type` | newer multifeature model (dendrite, soma and spine features; table `cell_type_multifeature_combo`). The only source for chandelier cells, PV-like cells and L1 interneurons |
| `consensus` | all of the above | every system that defines the term must agree, and the subclass must not contradict the broad type |

For example, only 29% of subclass neurogliaform cells are also neurogliaform by m-type and meso-type, and 56% of subclass `6P-IT` cells are `L6CT` in the multifeature model. Likewise, `broad_type` and `cell_type` often come from different models: 12% of "inhibitory" cells have a subclass label that isn't an interneuron class. The tool reports both kinds of disagreement and ranks those cells last.

The vocabulary lives in [`src/microns_finder/vocab.yaml`](src/microns_finder/vocab.yaml). It covers:
- glia: astrocyte, oligodendrocyte, OPC, microglia, pericyte;
- excitatory classes: L2/3, L4, L5 IT/ET/NP, L6 IT/CT, and others;
- inhibitory classes: basket, PV basket, CCK-like basket, chandelier, Martinotti, putative SST, neurogliaform, bipolar/VIP, layer 1 interneurons, PTC/DTC/ITC/STC, and others.

Each entry has synonyms. Some entries require a label system in every mode: "PV basket" needs the multifeature PV label, and "Martinotti" needs MC in both systems. "Layer 1 interneuron" means any inhibitory soma in L1. Molecular names such as PV, SST, VIP and CCK are morphology-based proxies; EM has no molecular labels.

### Layers

Layers are assigned from soma depth below the pia, in standard_transform space. MICrONS has no official layer table, so the boundaries were derived from the data: each one is the depth that best separates the excitatory classes on either side of it.

| Layer | Depth (µm) | Boundary set by |
| --- | --- | --- |
| L1 | 0-85 | neuronal density reaching half its L2 value |
| L2 | 85-175 | L2a-c vs L3a-b m-types |
| L3 | 175-250 | 23P vs 4P |
| L4 | 250-365 | 4P vs 5P |
| L5 | 365-510 | 5P-IT vs 6P |
| L6 | 510-720 | below 99% of 6P somata |
| WM | over 720 | |

Across the volume, the L2-L6 boundaries vary by about ±10 µm, L1/L2 by about ±12 µm and L6/WM by about ±25 µm (deeper toward the higher visual areas). [`scripts/derive_layer_boundaries.py`](scripts/derive_layer_boundaries.py) recomputes them for any release, and a live test checks that they still match the data.

**The white matter is mostly unlabeled.** 92% of the 12,841 single-nucleus segments below 720 µm (16,055 nuclei in all) have no cell-type call, so "an astrocyte in the white matter" draws on about 50 labeled cells.

## Reproducibility

- Results are deterministic for a given version, query and `--seed`.
- Quote **nucleus IDs**. Root IDs change whenever a cell is proofread.
- Use `--version` to query another public release (`microns-finder cache --version 1822`).
- Run the tests with `pytest` (offline, synthetic data) and `pytest -m live` (against the real data: every term returns cells, the layer boundaries still fit, and links round-trip).
- [`docs/verification.md`](docs/verification.md) has one link per vocabulary term for checking by eye. Regenerate it with `scripts/make_verification_sheet.py`.

## Related tools

- [SorenGrubb/microns-neuroglancer-tool](https://github.com/SorenGrubb/microns-neuroglancer-tool): a self-contained page for identifying the cell at a coordinate, filtering cells by type, layer and vessel proximity, expert-verified identifications, and community reporting. It complements this tool: it's coordinate- and click-driven, this one is language- and script-driven.
- [AllenNeuralDynamics/neuroglancer-chat](https://github.com/AllenNeuralDynamics/neuroglancer-chat): a chat agent that controls Neuroglancer views and layers.
- [nglui](https://github.com/CAVEconnectome/NeuroglancerAnnotationUI) and [CAVEclient](https://github.com/CAVEconnectome/CAVEclient): the libraries this tool is built on.
- [MICrONS tutorial](https://tutorial.microns-explorer.org/): official documentation for the tables used here.

## Citing

If you use this tool, please cite the dataset and the papers behind the labels you rely on:

- The MICrONS Consortium. Functional connectomics spanning multiple areas of mouse visual cortex. *Nature* 640, 435-447 (2025). https://doi.org/10.1038/s41586-025-08790-w
- Elabbady et al. Perisomatic ultrastructure efficiently classifies cells in mouse cortex. *Nature* 640, 478-486 (2025). https://www.nature.com/articles/s41586-024-07765-7
- Schneider-Mizell et al. Inhibitory specificity from a connectomic census of mouse visual cortex. *Nature* 640, 448-458 (2025). https://doi.org/10.1038/s41586-024-07780-8

Also cite this repository ([CITATION.cff](CITATION.cff)). The MICrONS data are released under CC BY 4.0. The code is MIT licensed.

Built with [Claude Code](https://claude.com/claude-code).
