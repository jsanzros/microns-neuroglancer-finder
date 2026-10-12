"""High-level entry point tying the cell table, queries and links together."""

from __future__ import annotations

import pandas as pd

from . import config
from .data import known_labels, load_cells, make_client
from .links import connection_links, make_link
from .query import FindResult, find_cells
from .synapses import Connection, SynapseResult, find_synapses
from .vocab import resolve


class Finder:
    """Query MICrONS cells at one materialization version.

    The CAVE client is created lazily: finding cells only needs the cached
    table, while short links, segment labels and synapses need the server.
    """

    def __init__(self, version: int = config.DEFAULT_VERSION, refresh: bool = False, client=None):
        self.version = version
        self._client = client
        self.cells = load_cells(version, refresh=refresh, client=client)

    @property
    def client(self):
        if self._client is None:
            self._client = make_client(self.version)
        return self._client

    def resolve(self, text: str):
        return resolve(text, known_labels(self.cells))

    def find(self, term=None, **kwargs) -> FindResult:
        """See `microns_finder.query.find_cells` for the keyword arguments."""
        result = find_cells(self.cells, term, **kwargs)
        result.params["version"] = self.version
        return result

    def lookup(self, ids) -> pd.DataFrame:
        """Rows for root IDs or nucleus IDs (either kind is accepted)."""
        ids = [int(i) for i in (ids if isinstance(ids, (list, tuple, set)) else [ids])]
        rows = self.cells[self.cells.root_id.isin(ids) | self.cells.nucleus_id.isin(ids)]
        return rows.reset_index(drop=True)

    def link(self, cells, *, shorten: bool = True, title: str | None = None, offline: bool = False, **kwargs) -> str:
        """Neuroglancer URL for a FindResult, a cell-table DataFrame, or a list of IDs."""
        if isinstance(cells, FindResult):
            if title is None and cells.term is not None:
                title = f"{cells.term.label} | MICrONS v{self.version}"
            cells = cells.cells
        elif not isinstance(cells, pd.DataFrame):
            cells = self.lookup(cells)
        client = None if offline else self.client
        return make_link(cells, client, shorten=shorten and not offline, title=title or f"MICrONS v{self.version}", **kwargs)

    def synapses(self, pre=None, post=None, **kwargs) -> SynapseResult:
        """Pairs of cells connected by synapses, `pre` onto `post` (e.g. "neurogliaform", "martinotti").

        See `microns_finder.synapses.find_synapses` for the keyword arguments.
        """
        result = find_synapses(self.client, self.cells, pre, post, **kwargs)
        result.params["version"] = self.version
        return result

    def connection_links(
        self, connection: Connection, *, zoom: int = 3, shorten: bool = True, offline: bool = False, title: str | None = None
    ) -> tuple[str, list[str]]:
        """Overview link for a pair from `synapses` (both cells, every synapse) and up to `zoom` links,
        each zoomed in on one synapse, largest first."""
        client = None if offline else self.client
        title = title or f"synapses | MICrONS v{self.version}"
        return connection_links(connection, client, shorten=shorten and not offline, zoom=zoom, title=title)
