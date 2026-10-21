"""`agentsmon restart`: the dashboard's restart action from the command line.

Used by installers that change an agent's configuration (e.g. a new MCP server), so a running
agent reloads it without anyone clicking ↻. Each restart resumes the pinned conversation exactly
like the dashboard does; agents that are not running are left alone.
"""
from . import config, detect


def run(names, every=False) -> int:
    from .dashboard import _agent_action
    cfg = config.load()
    running = {a["name"] for a in detect.discover_agents(config.agent_matches(cfg)) if a.get("alive")}
    configured = [a["name"] for a in cfg.get("agents", []) if a.get("name")]
    if every:
        targets = [n for n in configured if n in running and next(
            (a for a in cfg["agents"] if a["name"] == n), {}).get("enabled", True)]
    else:
        unknown = [n for n in names if n not in configured]
        if unknown:
            print("Unknown agent(s): " + ", ".join(unknown))
            return 1
        targets = list(names)
    if not targets:
        print("No running supervised agents to restart.")
        return 0
    failed = 0
    for name in targets:
        ok, message = _agent_action(name, "restart")
        print(("✓ " if ok else "✗ ") + f"{name}: {message}")
        failed += not ok
    return 1 if failed else 0
