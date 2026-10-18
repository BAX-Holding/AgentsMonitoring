"""Decline one known optional UI experiment; never answer permission/login dialogs."""
import re

from . import detect


def optional_renderer_dialog(text):
    clean = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', text)
    lines = [line.strip().lstrip('>❯ ').strip() for line in clean.splitlines() if line.strip()]
    allowed = {'Try the new fullscreen renderer?', '1. Yes', '2. Not now',
               'Enter to confirm · Esc to cancel', 'Enter to confirm · Escape to cancel'}
    return (set(lines) <= allowed and {'Try the new fullscreen renderer?', '1. Yes', '2. Not now'} <= set(lines))


def dismiss_optional_renderer(name):
    r = detect._run([detect._tmux_bin(), 'capture-pane', '-p', '-t', name])
    if not r or r.returncode != 0 or not optional_renderer_dialog(r.stdout):
        return False
    # Only the exact, fully recognized optional feature dialog has a safe decline.
    sent = detect._run([detect._tmux_bin(), 'send-keys', '-t', name, '2', 'Enter'])
    return bool(sent and sent.returncode == 0)
