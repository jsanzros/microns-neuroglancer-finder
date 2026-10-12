"""CLI helpers that don't need data."""

import pytest

from microns_finder.cli import main
from microns_finder.setup_helpers import CLIENTS, install_skill, mcp_config, skill_source


@pytest.mark.parametrize("app", CLIENTS)
def test_mcp_config_for_every_app(app):
    text = mcp_config(app)
    assert "microns-finder" in text


def test_install_skill_to_folder(tmp_path):
    [path] = install_skill(dest=tmp_path)
    assert path == tmp_path / "find-cells" / "SKILL.md"
    assert path.read_text(encoding="utf-8") == skill_source().read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8").startswith("---\nname: find-cells")


def test_cli_layers_and_config(capsys):
    assert main(["layers"]) == 0
    assert "L6" in capsys.readouterr().out
    assert main(["mcp-config", "codex"]) == 0
    assert "codex mcp add" in capsys.readouterr().out
