"""MCP server: lets any MCP-capable AI (Claude, ChatGPT, Gemini/Antigravity, Codex, Copilot, Cursor...) find MICrONS cells.

Local (stdio, for desktop apps and coding agents):   microns-finder-mcp
Remote (Streamable HTTP, for ChatGPT / Gemini web):   microns-finder-mcp --http --port 8000
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import os
import sys
import threading
from typing import Annotated, Literal

from pydantic import Field

from . import __version__, config, service

INSTRUCTIONS = """\
Tools for the MICrONS cubic millimeter of mouse visual cortex (electron microscopy, datastack minnie65_public).
Use them whenever the user wants to see, find or pick example cells (by type, layer, area or proofreading) or look up a cell by ID.

Rules:
- Never invent root IDs, nucleus IDs, coordinates or links. Report only what the tools return.
- Reply with the link first, then a short table of the returned cells (nucleus ID, root ID, labels, layer, depth, area, proofreading in a few words), then the notes, which carry the caveats. Mention the materialization version, and once per conversation tell the user that the viewer asks for a Google sign-in the first time.
- One find_cells call per requested cell type; call it several times for multi-part requests.
- "Layer" means soma position (depth below the pia): L1 0-85 µm, L2 85-175, L3 175-250, L4 250-365, L5 365-510, L6 510-720, WM over 720. Type names such as "L5 ET" are types, not positions; add a layer only when the user asks for a position.
- Use labels="consensus" when the user wants confident or typical examples, or when a note reports low agreement between label systems.
- PV, SST, VIP and CCK are morphology-based proxies; EM has no molecular labels. Say so.
- For "another one", call again with a different seed or with exclude set to the IDs already shown.
- Nucleus IDs are stable across releases; root IDs change when cells are proofread.
"""

mcp = None  # created in build_server(); module-level for `mcp dev`-style tooling
_finder = None
_finder_lock = threading.Lock()
_version = int(os.environ.get("MICRONS_FINDER_VERSION", config.DEFAULT_VERSION))


def set_finder(finder) -> None:
    """Use a prepared Finder (tests, notebooks)."""
    global _finder
    _finder = finder


def _get_finder():
    global _finder
    with _finder_lock:
        if _finder is None:
            from .finder import Finder

            _finder = Finder(version=_version)
        return _finder


def _quiet(func):
    """Send anything a library prints to stderr: stdout carries the MCP protocol in stdio mode."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return func(*args, **kwargs)

    return wrapper


@_quiet
def find_cells(
    cell_type: Annotated[
        str,
        Field(
            description='Cell type in plain words, optionally with a position, e.g. "astrocyte", "neurogliaform cell", '
            '"L5 ET", "basket cell in layer 4", "oligodendrocyte in the white matter". Synonyms and raw MICrONS labels '
            '(23P, 6P-CT, L2a, AltBasket) work; call list_cell_types if unsure. Empty means any cell.'
        ),
    ] = "",
    layer: Annotated[str | None, Field(description='Soma layer(s): "L1", "L2", "L3", "L2/3", "L4", "L5", "L6", "WM" (white matter), or a comma-separated list.')] = None,
    area: Annotated[str | None, Field(description='Visual area: "V1", "RL", "AL", "LM", or "HVA" (= RL, AL, LM).')] = None,
    labels: Annotated[
        Literal["subclass", "mtype", "meso", "consensus"],
        Field(description="Label system: subclass (default, AIBS metamodel plus expert labels), mtype (morphological types), meso (newer multifeature model), consensus (all systems that define the type agree)."),
    ] = "subclass",
    proofread: Annotated[
        Literal["any", "dendrite", "axon", "both", "full"] | None,
        Field(description='Only proofread cells. "full" = clean dendrite and fully extended axon. For glia use "any". Proofread cells are ranked first anyway.'),
    ] = None,
    n: Annotated[int, Field(ge=1, le=20, description="Number of cells (default 3; use 1 for a single cell or with synapses).")] = 3,
    seed: Annotated[int, Field(description="Change to get different example cells.")] = 0,
    synapses: Annotated[bool, Field(description="Add input and output synapse layers to the link (neurons only, first 3 cells).")] = False,
    expert: Annotated[bool, Field(description="Only cells whose subclass label is an expert manual annotation.")] = False,
    functional: Annotated[bool, Field(description="Only cells coregistered with two-photon functional imaging.")] = False,
    where: Annotated[
        dict[str, str] | None,
        Field(description='Extra filters on cell-table columns, e.g. {"mtype": "L4c"} or {"meso_type": "ChC,PV"} (comma = any of).'),
    ] = None,
    exclude: Annotated[list[str] | None, Field(description="Root or nucleus IDs already shown, to skip.")] = None,
) -> dict:
    """Find example cells in MICrONS and return a Neuroglancer link plus a table of the cells.

    The result has `link`, `cells` (nucleus_id, root_id, labels, layer, depth_um, visual_area, proofreading),
    `pool_size` (how many cells matched), `filters` (exactly what was applied) and `notes` (caveats to pass on),
    or `error` with `suggestions` if the cell type wasn't recognized.
    """
    where_lists = {k: [v.strip() for v in str(val).split(",") if v.strip()] for k, val in (where or {}).items()} or None
    return service.find(
        _get_finder(),
        cell_type,
        layer=layer,
        area=area,
        labels=labels,
        proofread=proofread,
        n=n,
        seed=seed,
        synapses=synapses,
        expert=expert,
        functional=functional,
        where=where_lists,
        exclude=exclude,
    )


@_quiet
def describe_cells(
    ids: Annotated[list[str], Field(description="Root IDs (18 digits) and/or nucleus IDs.")],
    synapses: Annotated[bool, Field(description="Add input and output synapse layers to the link.")] = False,
) -> dict:
    """Look up cells by root or nucleus ID: all their labels, layer, area and proofreading, plus a Neuroglancer link."""
    return service.show(_get_finder(), ids, synapses=synapses)


@_quiet
def list_cell_types(
    counts: Annotated[bool, Field(description="Also count matching cells per type (takes a second or two).")] = False,
) -> dict:
    """List the cell-type vocabulary: each type's key, label, synonyms and the MICrONS labels it maps to."""
    finder = _get_finder() if counts else None
    return {"cell_types": service.terms(finder, counts=counts)}


@_quiet
def layer_boundaries() -> dict:
    """The soma-depth boundaries used to assign cortical layers."""
    return service.layers()


TOOLS = (find_cells, describe_cells, list_cell_types, layer_boundaries)


def build_server():
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer(
        name="microns-finder",
        title="MICrONS cell finder",
        description="Find cells in the MICrONS mouse visual cortex EM dataset and open them in Neuroglancer.",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://github.com/jsanzros/microns-neuroglancer-finder",
    )
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
    for tool in TOOLS:
        server.tool(annotations=read_only)(tool)
    return server


def main(argv=None) -> int:
    global mcp, _version
    p = argparse.ArgumentParser(prog="microns-finder-mcp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--http", action="store_true", help="serve over Streamable HTTP instead of stdio")
    p.add_argument("--host", default="127.0.0.1", help="HTTP host (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="HTTP port (default 8000)")
    p.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        metavar="HOST",
        help="extra Host header to accept over HTTP, e.g. your tunnel's domain (repeatable)",
    )
    p.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="Origin header to accept over HTTP, e.g. https://chatgpt.com (repeatable; requests without one are accepted)",
    )
    p.add_argument(
        "--public",
        action="store_true",
        help="accept any Host/Origin header, for use behind a tunnel or proxy (turns off DNS-rebinding protection)",
    )
    p.add_argument("--version", type=int, default=_version, help=f"materialization version (default {config.DEFAULT_VERSION})")
    p.add_argument("--preload", action="store_true", help="load the cell table before serving")
    args = p.parse_args(argv)
    _version = args.version
    if args.preload:
        with contextlib.redirect_stdout(sys.stderr):
            _get_finder()

    mcp = build_server()
    if not args.http:
        mcp.run("stdio")
        return 0

    from mcp.server.transport_security import TransportSecuritySettings

    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", *args.allowed_host]
    origins = ["http://127.0.0.1:*", "http://localhost:*", *args.allowed_origin]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=not args.public, allowed_hosts=hosts, allowed_origins=origins
    )
    print(f"microns-finder MCP server on http://{args.host}:{args.port}/mcp", file=sys.stderr)
    mcp.run("streamable-http", host=args.host, port=args.port, transport_security=security)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
