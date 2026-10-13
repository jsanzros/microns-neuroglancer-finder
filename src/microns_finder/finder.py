"""High-level entry point tying the cell table, queries and links together."""

from __future__ import annotations

import warnings

import pandas as pd

from . import config
from .data import known_labels, load_cells, make_client
from .links import LinkWarning, connection_links, make_link
from .query import FindResult, find_cells
from .synapses import Connection, SynapseResult, find_synapses
from .vocab import resolve


NO_TOKEN_NOTE = (
    "No CAVE token found, so links are full-length URLs without cell labels in the segment list, and "
    "synapses aren't available. A free token unlocks them (see the README's Install section)."
)


class Finder:
    """Query MICrONS cells at one materialization version.

    The CAVE client is created lazily: finding cells only needs the cell table
    (built from CAVE, or the prebuilt snapshot when there is no token), while
    short links, segment labels and synapses need the server.
    """

    def __init__(self, version: int = config.DEFAULT_VERSION, refresh: bool = False, client=None, source: str = "auto"):
        self.version = version
        self._client = client
        self._online = True if client is not None else None
        self.cells = load_cells(version, refresh=refresh, client=client, source=source)

    @property
    def client(self):
        if self._client is None:
            self._client = make_client(self.version)
        return self._client

    @property
    def online(self) -> bool:
        """Whether the CAVE servers can be reached with a token (checked once)."""
        if getattr(self, "_online", None) is None:  # subclasses may skip __init__
            try:
                self.client
                self._online = True
            except RuntimeError:
                self._online = False
        return self._online

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
        if not offline and not self.online:
            warnings.warn(NO_TOKEN_NOTE, LinkWarning)
            if kwargs.pop("synapses", False):
                warnings.warn("Synapse layers need a CAVE token, so the link shows the cells only.", LinkWarning)
            offline = True
        client = None if offline else self.client
        return make_link(cells, client, shorten=shorten and not offline, title=title or f"MICrONS v{self.version}", **kwargs)

    def synapses(self, pre=None, post=None, **kwargs) -> SynapseResult:
        """Pairs of cells connected by synapses, `pre` onto `post` (e.g. "neurogliaform", "martinotti").

        See `microns_finder.synapses.find_synapses` for the keyword arguments.
        """
        if not self.online:
            raise ValueError("Finding synapses needs a free CAVE token for the MICrONS data (see the README's Install section).")
        result = find_synapses(self.client, self.cells, pre, post, **kwargs)
        result.params["version"] = self.version
        return result

    def connection_links(
        self, connection: Connection, *, zoom: int = 3, shorten: bool = True, offline: bool = False, title: str | None = None
    ) -> tuple[str, list[str]]:
        """Overview link for a pair from `synapses` (both cells, every synapse) and up to `zoom` links,
        each zoomed in on one synapse, largest first."""
        if not offline and not self.online:
            warnings.warn(NO_TOKEN_NOTE, LinkWarning)
            offline = True
        client = None if offline else self.client
        title = title or f"synapses | MICrONS v{self.version}"
        return connection_links(connection, client, shorten=shorten and not offline, zoom=zoom, title=title)
