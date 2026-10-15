"""`agentsmon uninstall` — stop the dashboard/keepalive and remove config + state."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import config, service


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

    for d in (config.DEFAULT_PATH.parent, Path.home() / ".local" / "state" / "agentsmon",
              Path.home() / ".agentsmon-src"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            print(f"  removed {d}")

    subprocess.run([os.sys.executable, "-m", "pip", "uninstall", "-y", "agents-monitoring"],
                   capture_output=True)
    print("\n✓ Agents Monitoring removed. (Your tmux agents keep running untouched.)")
    return 0
