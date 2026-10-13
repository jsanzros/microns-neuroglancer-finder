"""Build notebooks/try_microns_finder.ipynb, the no-install Colab walkthrough.

Usage (needs nbformat; --execute also needs nbclient and ipykernel):
    python scripts/build_notebook.py v0.1.2            # write the notebook, installing that release tag
    python scripts/build_notebook.py v0.1.2 --execute  # also run it like a newcomer and keep the outputs

--execute runs every cell except the install cell (the package must already be installed here) with
an empty home folder and cache, so there's no CAVE token and the prebuilt cell table is used, as in Colab.
"""
import os
import sys
import tempfile
from pathlib import Path

import nbformat as nbf

REPO = Path(__file__).resolve().parents[1]
TAG = sys.argv[1]  # release tag the notebook installs, e.g. v0.1.2
COLAB = "https://colab.research.google.com/github/jsanzros/microns-neuroglancer-finder/blob/main/notebooks/try_microns_finder.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell
cells = [
    md(f"""# Try microns-finder

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({COLAB})

Find cells in the [MICrONS](https://www.microns-explorer.org/cortical-mm3) cubic millimeter of mouse visual cortex by asking for them in plain words, and open them in Neuroglancer.

**No installation and no account needed.** Run the cells from top to bottom (Shift+Enter). The first one takes about 30 seconds.

Without a CAVE token, the tool uses a prebuilt copy of the MICrONS cell table (release v1926, 144,120 nuclei). That's enough to search cells by type, layer, area and proofreading. A free token, covered at the end, adds synapses and shorter links with labels."""),
    code(f"""# Install the tool. This skips the extra packages of its AI (MCP) server, which this notebook doesn't need.
%pip install -q caveclient nglui pandas pyarrow pyyaml
%pip install -q --no-deps "git+https://github.com/jsanzros/microns-neuroglancer-finder@{TAG}\""""),
    code("""import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from IPython.display import HTML, display
from microns_finder import Finder, service
from microns_finder.finder import NO_TOKEN_NOTE

f = Finder()  # without a token this downloads the prebuilt cell table (8 MB)
print(f"{len(f.cells):,} cells loaded from MICrONS release v{f.version}")


def show(request, **options):
    \"\"\"Find cells, show them as a table and a Neuroglancer link.\"\"\"
    options.setdefault("n", 3)
    p = service.find(f, request, **options)
    if "error" in p:
        print(p["error"])
        return
    print(f"{p['pool_size']:,} cells match; showing {p['n_returned']}.")
    table = pd.DataFrame(p["cells"])[["nucleus_id", "subclass", "mtype", "meso_type", "layer", "depth_um", "visual_area", "proofreading"]]
    display(table)
    display(HTML(f'<p><a href="{p["link"]}" target="_blank"><b>Open these cells in Neuroglancer ↗</b></a></p>'))
    for note in p["notes"]:
        if note != NO_TOKEN_NOTE:  # explained at the top
            print("note:", note)"""),
    md("""## Ask for cells

Each request returns three example cells by default, and a link that opens them in Neuroglancer with each cell colored. Click a soma point in the `somata` layer to see its labels, depth and proofreading.

The first time you open a link, Neuroglancer asks you to **sign in with Google**. It's free; MICrONS uses it to serve the segmentation."""),
    code('show("astrocyte in layer 1")'),
    code('show("oligodendrocyte in the white matter")'),
    md("""MICrONS has three cell-type classifications, and they don't always agree. `labels="consensus"` keeps only cells that every classification calls the requested type:"""),
    code('show("neurogliaform cell", labels="consensus")'),
    code('show("chandelier cell")'),
    md("""Change `seed` to get other examples, or `n` for more cells. `proofread` keeps only manually proofread cells:"""),
    code('show("basket cell in layer 4", seed=1)'),
    code('show("L5 ET", area="V1", proofread="full", n=1)'),
    md("""## Your turn

Edit the request and run the cell. Plain names work, such as "microglia", "Martinotti cell", "L2/3 pyramidal", "VIP interneuron", "pericyte" or "L6 corticothalamic". So do raw MICrONS labels like `23P` or `L4c`. The next cell lists every cell type the tool knows."""),
    code('show("microglia")'),
    code("""pd.DataFrame(service.terms())[["key", "label", "synonyms"]]"""),
    md("""## Optional: add a free CAVE token

A token unlocks synapses (e.g. "basket cells onto L2/3 pyramidal cells"), shorter links with cell labels, and other MICrONS releases.

1. Open https://global.daf-apis.com/auth/api/v1/create_token, sign in with Google, accept the MICrONS terms if asked, and copy the token.
2. In Colab, click the **key icon** (Secrets) in the left sidebar, add a secret named `CAVE_TOKEN` with the token as its value, and allow this notebook to use it.
3. Run the next two cells.

Keep the token private: it's like a password for your MICrONS access. Secrets keep it out of the notebook itself."""),
    code("""from caveclient import CAVEclient

try:
    from google.colab import userdata
    token = userdata.get("CAVE_TOKEN")
except Exception:  # not in Colab, or no secret yet
    token = None

if token:
    CAVEclient().auth.save_token(token=token, overwrite=True)
    f = Finder()
    print("Token saved. Synapses and short links are available:", f.online)
else:
    print("No CAVE_TOKEN secret found, so the notebook continues without a token.")"""),
    code("""if f.online:
    s = service.synapses(f, "basket cell onto L2/3 pyramidal", n=1)
    for pair in s.get("pairs", []):
        print(f"{pair['n_synapses']} synapses from nucleus {pair['pre']['nucleus_id']} onto nucleus {pair['post']['nucleus_id']}")
        display(HTML(f'<p><a href="{pair["link"]}" target="_blank"><b>Open both cells and their synapses ↗</b></a></p>'))
    for note in s.get("notes", []):
        print("note:", note)
    if "error" in s:
        print(s["error"])
else:
    print("Add a token above to try synapses.")"""),
    md("""## Next steps

- **Use it with your AI assistant:** ChatGPT, Gemini, Claude, Codex, Copilot or Cursor can answer requests like "show me a microglia" with real cells through the tool's MCP server. See the [README](https://github.com/jsanzros/microns-neuroglancer-finder#connect-your-ai).
- **Install it on your computer:** `pip install "git+https://github.com/jsanzros/microns-neuroglancer-finder"`.
- **Cite it:** [doi.org/10.5281/zenodo.23326398](https://doi.org/10.5281/zenodo.23326398), together with the MICrONS papers listed in the README.

The cell table is derived from the MICrONS data (MICrONS Consortium, *Nature* 2025), released under CC BY 4.0."""),
]
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata = {
    "colab": {"provenance": [], "name": "try_microns_finder.ipynb"},
    "kernelspec": {"display_name": "Python 3", "name": "python3"},
    "language_info": {"name": "python"},
}
out = REPO / "notebooks" / "try_microns_finder.ipynb"
out.parent.mkdir(exist_ok=True)
nbf.write(nb, out)
print("wrote", out)


if "--execute" in sys.argv:
    from nbclient import NotebookClient

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        os.environ.update(HOME=str(home), USERPROFILE=str(home), MICRONS_FINDER_CACHE=str(Path(tmp) / "cache"))
        install = nb.cells[1].source
        nb.cells[1].source = "pass  # install skipped: the package is already installed here"
        NotebookClient(nb, timeout=600, kernel_name="python3").execute()
        nb.cells[1].source, nb.cells[1].outputs = install, []
    nbf.write(nb, out)
    print("executed and saved with outputs")
