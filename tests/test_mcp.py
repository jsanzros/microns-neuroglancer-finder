"""MCP server tests.

Offline: tool schemas and calls in-process, on the synthetic table.
Live (pytest -m live): launch the real server over stdio and over HTTP and call it
with the official MCP client, the way ChatGPT, Gemini, Codex or Claude would.
"""

import asyncio
import json
import socket
import subprocess
import sys
import time

import pytest

mcp = pytest.importorskip("mcp")
from mcp import Client, StdioServerParameters  # noqa: E402

from microns_finder import mcp_server  # noqa: E402
from microns_finder.finder import Finder  # noqa: E402


class OfflineFinder(Finder):
    """A Finder on a given table that never contacts CAVE."""

    def __init__(self, cells):
        self.version = 1926
        self._client = None
        self.cells = cells

    def link(self, cells, **kwargs):
        kwargs.update(offline=True, shorten=False)
        return super().link(cells, **kwargs)


def _payload(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def _call(server_or_target, name, arguments=None):
    async def run():
        async with Client(server_or_target) as client:
            return await client.call_tool(name, arguments or {})

    return asyncio.run(run())


@pytest.fixture
def server(cells):
    mcp_server.set_finder(OfflineFinder(cells))
    yield mcp_server.build_server()
    mcp_server.set_finder(None)


def test_tools_and_instructions(server):
    async def run():
        async with Client(server) as client:
            tools = await client.list_tools()
            return client, {t.name: t for t in tools.tools}

    client, tools = asyncio.run(run())
    assert set(tools) == {"find_cells", "describe_cells", "list_cell_types", "layer_boundaries"}
    props = tools["find_cells"].input_schema["properties"]
    assert {"cell_type", "layer", "area", "labels", "proofread", "n", "seed", "synapses", "where", "exclude"} <= set(props)
    assert "Layer" in mcp_server.INSTRUCTIONS and "Never invent" in mcp_server.INSTRUCTIONS
    assert all(t.annotations.read_only_hint for t in tools.values())


def test_find_cells_tool(server):
    data = _payload(_call(server, "find_cells", {"cell_type": "astrocyte in layer 1", "n": 5}))
    assert data["term"]["key"] == "astrocyte"
    assert {c["root_id"] for c in data["cells"]} == {"101", "102"}
    assert data["link"].startswith("https://spelunker.cave-explorer.org/")
    assert data["link_contents"]["viewer_note"]


def test_find_cells_where_and_exclude(server):
    data = _payload(_call(server, "find_cells", {"where": {"mtype": "L2a,L3a"}, "n": 5}))
    assert {c["root_id"] for c in data["cells"]} == {"107", "108"}
    data = _payload(_call(server, "find_cells", {"cell_type": "astrocyte", "layer": "L1", "exclude": ["102"]}))
    assert [c["root_id"] for c in data["cells"]] == ["101"]


def test_unknown_type_returns_suggestions(server):
    data = _payload(_call(server, "find_cells", {"cell_type": "astrocite"}))
    assert "error" in data and "astrocyte" in data["suggestions"]


def test_describe_and_vocabulary_tools(server):
    data = _payload(_call(server, "describe_cells", {"ids": ["108", "999"]}))
    assert [c["nucleus_id"] for c in data["cells"]] == [8] and data["missing"] == ["999"]
    vocab = _payload(_call(server, "list_cell_types"))
    assert any(t["key"] == "chandelier" for t in vocab["cell_types"])
    layers = _payload(_call(server, "layer_boundaries"))
    assert layers["layers"][0]["layer"] == "L1"


# ---- live: the real server process over both transports --------------------------------


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.live
def test_live_stdio_server():
    params = StdioServerParameters(command=sys.executable, args=["-m", "microns_finder.mcp_server"])
    data = _payload(_call(params, "find_cells", {"cell_type": "neurogliaform", "labels": "consensus", "n": 2}))
    assert data["n_returned"] == 2 and "nglstate" in data["link"]
    assert all(c["subclass"] == "NGC" and c["meso_type"] == "NGC" for c in data["cells"])


@pytest.mark.live
def test_live_http_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "microns_finder.mcp_server", "--http", "--port", str(port), "--preload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.5)
        data = _payload(_call(f"http://127.0.0.1:{port}/mcp", "find_cells", {"cell_type": "oligodendrocyte in the white matter", "n": 1}))
        assert data["cells"][0]["layer"] == "WM" and "nglstate" in data["link"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
