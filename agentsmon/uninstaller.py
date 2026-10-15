"""`agentsmon uninstall` — stop the dashboard/keepalive and remove config + state."""
from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

from . import config, service


def _remove_cli_wrapper() -> bool:
    """Remove only the unmodified wrapper produced by install.sh for this source.

    Leave symlinks, other owners, custom scripts and wrappers for other checkouts alone.
    """
    path = Path.home() / ".local/bin/agentsmon"
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 8192:
            return False
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) != 2 or lines[0] != "#!/bin/sh":
            return False
        args = shlex.split(lines[1])
        if len(args) != 7 or args[:2] != ['exec', 'env'] or args[4:] != ['-m', 'agentsmon', '$@']:
            return False
        for source in (service._pythonpath(), str(Path.home() / '.agentsmon-src')):
            expected = f'exec env PYTHONPATH="{source}" "{args[3]}" -m agentsmon "$@"'
            if lines[1] == expected:
                path.unlink()
                return True
    except FileNotFoundError:
        pass
    except (UnicodeError, ValueError):
        pass                           # a custom/non-shell launcher, not ours
    return False


def run(yes: bool = False) -> int:
    print("This stops the dashboard + keepalive and removes config + state.")
    if not yes:
        try:
            if input("Continue? (y/N): ").strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 0
        except EOFError:
            print("Aborted — no terminal; rerun with --yes.")
            return 0

    # 1) Remove the cron launcher lines, then stop the running dashboard.
    service.uninstall_cron()
    print("  removed cron launcher")
    service.stop_dashboard()
    if shutil.which("pkill"):
        # Match complete Python module/console-script invocations, not a shell merely
        # mentioning keepalive. Both the cron one-shot and manual --loop are covered.
        pattern = (r"^([^[:space:]]*/)?[Pp]ython[0-9.]* "
                   r"(-m agentsmon|([^[:space:]]*/)?agentsmon) keepalive( --loop)?$")
        subprocess.run(["pkill", "-u", str(os.getuid()), "-f", "--", pattern],
                       capture_output=True, timeout=10)
        print("  stopped running dashboard/keepalive")

    if _remove_cli_wrapper():
        print("  removed ~/.local/bin/agentsmon")
    print("  Remove any Agents Monitoring PATH entry from your shell rc files manually; they were not edited.")

    for d in (config.DEFAULT_PATH.parent, Path.home() / ".local" / "state" / "agentsmon",
              Path.home() / ".agentsmon-src"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            print(f"  removed {d}")

    subprocess.run([os.sys.executable, "-m", "pip", "uninstall", "-y", "agents-monitoring"],
                   capture_output=True)
    print("\n✓ Agents Monitoring removed. (Your tmux agents keep running untouched.)")
    return 0
