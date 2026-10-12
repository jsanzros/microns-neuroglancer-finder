"""Set-up helpers: MCP config snippets for each AI app, and installing the agent skill."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SERVER_NAME = "microns-finder"

# Where each agent reads user-level skills (the open Agent Skills format).
SKILL_DIRS = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".agents" / "skills",  # also read by other agents that follow .agents/
    "antigravity": Path.home() / ".gemini" / "antigravity-cli" / "skills",
}

CLIENTS = ("claude-code", "claude-desktop", "codex", "antigravity", "cursor", "vscode", "chatgpt", "gemini-web")


def server_command() -> str:
    """Absolute path of the `microns-finder-mcp` executable (GUI apps often lack the shell's PATH)."""
    found = shutil.which("microns-finder-mcp")
    if found:
        return str(Path(found).resolve())
    scripts = Path(sys.executable).parent
    for name in ("microns-finder-mcp.exe", "microns-finder-mcp"):
        if (scripts / name).exists():
            return str(scripts / name)
    return "microns-finder-mcp"


def _json(obj) -> str:
    return json.dumps(obj, indent=2)


def mcp_config(client: str) -> str:
    """Instructions and config text for connecting `client` to the MCP server."""
    cmd = server_command()
    servers = {"mcpServers": {SERVER_NAME: {"command": cmd, "args": []}}}
    toml_cmd = cmd.replace("\\", "\\\\")
    http = (
        "1. Start the server:  microns-finder-mcp --http --public --port 8000 --preload\n"
        "   (--public accepts requests addressed to the tunnel's domain)\n"
        "2. Give it a public HTTPS address with a tunnel, e.g.:  cloudflared tunnel --url http://127.0.0.1:8000\n"
        "   (or your provider's own tunnel).\n"
        "3. The MCP URL is  https://<tunnel-domain>/mcp  (no authentication).\n"
        "   Anyone with that URL can use the server while it runs (read-only public data, but your CAVE token\n"
        "   makes the short links), so don't share it and stop the tunnel when you're done.\n"
    )
    texts = {
        "claude-code": f"Run in a terminal:\n\n  claude mcp add {SERVER_NAME} -- \"{cmd}\"\n\n"
        "(Or install the Claude Code plugin, which uses the command line instead of MCP.)",
        "claude-desktop": "Add this to claude_desktop_config.json (Settings > Developer > Edit Config), then restart Claude:\n\n"
        + _json(servers),
        "codex": f"Run in a terminal (works for Codex CLI, the IDE extension and the ChatGPT desktop app's Codex):\n\n"
        f"  codex mcp add {SERVER_NAME} -- \"{cmd}\"\n\nor add to ~/.codex/config.toml:\n\n"
        f"[mcp_servers.{SERVER_NAME}]\ncommand = \"{toml_cmd}\"\ntool_timeout_sec = 120",
        "antigravity": "Add this to ~/.gemini/config/mcp_config.json (Antigravity CLI, the successor of Gemini CLI):\n\n"
        + _json(servers),
        "cursor": "Add this to ~/.cursor/mcp.json:\n\n" + _json(servers),
        "vscode": "Add this to .vscode/mcp.json in your workspace (GitHub Copilot agent mode):\n\n"
        + _json({"servers": {SERVER_NAME: {"type": "stdio", "command": cmd, "args": []}}}),
        "chatgpt": "ChatGPT connects only to remote HTTPS MCP servers, through Developer Mode (paid plans; on workspace\n"
        "plans an admin enables it).\n\n" + http + "\n4. In ChatGPT, enable Developer Mode and create a custom MCP app/connector with that URL and\n"
        "   no authentication (the menu has moved between releases; see OpenAI's help article\n"
        "   'Developer mode and MCP apps in ChatGPT').",
        "gemini-web": "The Gemini app connects to custom remote MCP servers under Connected Apps (availability depends on\n"
        "account type and region).\n\n" + http + "\n4. In the Gemini web app, add a custom connected app with that URL.",
    }
    if client not in texts:
        raise ValueError(f"Unknown app {client!r}. Choose one of: {', '.join(CLIENTS)}")
    return texts[client]


def skill_source() -> Path:
    """SKILL.md shipped in the wheel, or the repository copy in a development install."""
    packaged = Path(__file__).parent / "skills" / "find-cells" / "SKILL.md"
    if packaged.exists():
        return packaged
    repo = Path(__file__).resolve().parents[2] / "skills" / "find-cells" / "SKILL.md"
    if repo.exists():
        return repo
    raise FileNotFoundError("SKILL.md not found in the package or the repository.")


def install_skill(agents=("claude", "codex", "antigravity"), dest: Path | None = None) -> list[Path]:
    """Copy the find-cells skill where the given agents (or `dest`) will discover it."""
    targets = [Path(dest)] if dest else [SKILL_DIRS[a] for a in agents]
    written = []
    for base in targets:
        folder = base / "find-cells"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill_source(), folder / "SKILL.md")
        written.append(folder / "SKILL.md")
    return written
