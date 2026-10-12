# AGENTS.md

Guidance for AI coding agents (Codex, Copilot, Cursor, Antigravity, Claude Code and others) working in this repository.

## What this is

`microns-finder` finds cells in the MICrONS mouse visual cortex EM dataset (CAVE datastack `minnie65_public`) by cell type, layer, area and proofreading status, finds pairs of cells connected by synapses, and builds Neuroglancer (Spelunker) links, including zoomed-in links to individual synapses. There are three interfaces over one core:
- the Python library (`src/microns_finder/`),
- the command line `microns-finder`,
- the MCP server `microns-finder-mcp`.

## If the user wants to see MICrONS cells

- If the `microns-finder` MCP tools are connected (`find_cells`, `describe_cells`, `find_synapses`, `list_cell_types`, `layer_boundaries`), use them.
- Otherwise use the command line with `--json`, following [`skills/find-cells/SKILL.md`](skills/find-cells/SKILL.md). That file is the authoritative usage guide.
- In either case, never invent root IDs, nucleus IDs or links; report only what the tool returns.

## Development

- **Setup:** `pip install -e ".[dev]"`. A CAVE token is needed for anything that touches the data: queries the first time, short links, synapses, and live tests.
- **Tests:**
  - `pytest` runs the offline tests on a synthetic table and synthetic synapses (`tests/conftest.py`), in about 3 seconds.
  - `pytest -m live` runs against the real data. It also checks that every vocabulary term returns cells, that the layer boundaries still fit the data, and that the MCP server works over stdio and HTTP.
- **Layout:**

  | File | Role |
  | --- | --- |
  | `data.py` | downloads and caches the cell table; bump `CACHE_SCHEMA` when its columns change |
  | `vocab.yaml`, `vocab.py` | cell-type vocabulary and term resolution |
  | `layers.py` | layer boundaries |
  | `query.py` | filtering, ranking, request parsing |
  | `synapses.py` | synapses between two cell types: the search and the ranking of connected pairs |
  | `links.py` | Neuroglancer states, including the per-synapse zoomed-in links |
  | `service.py` | JSON results shared by the CLI and MCP |
  | `cli.py` | the command line |
  | `mcp_server.py` | the MCP server |
  | `setup_helpers.py` | `mcp-config` and `install-skill` |

- **Adding a cell type:** edit `src/microns_finder/vocab.yaml` (the file explains the fields), then run both test suites. Keep molecular names (PV, SST, VIP) marked as morphology-based proxies.
- **Command-line output:** keep `--json` output and MCP tool results identical; both come from `service.py`.
- **MCP stdio mode:** stdout carries the protocol. Never print to stdout in code reachable from MCP tools; the server redirects library output to stderr.
- **New public release:**
  1. Run `python scripts/derive_layer_boundaries.py --version N` and update `layers.py` if the boundaries moved.
  2. Run `pytest -m live`.
  3. Update `DEFAULT_VERSION` in `config.py`.
  4. Regenerate `docs/verification.md` with `python scripts/make_verification_sheet.py`.
