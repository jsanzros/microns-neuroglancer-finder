"""Find cells in the MICrONS EM dataset by type, layer and area, and open them in Neuroglancer.

>>> from microns_finder import Finder
>>> f = Finder()                       # downloads the cell table once, then works offline
>>> res = f.find("astrocyte", layer="L1", n=3)
>>> res.summary_table()
>>> f.link(res)                        # short Spelunker/Neuroglancer URL
"""

__version__ = "0.1.0"

from .finder import Finder  # noqa: E402

__all__ = ["Finder", "__version__"]
