"""Decline one known optional UI experiment; never answer permission/login dialogs."""
import re

from . import detect


def optional_renderer_dialog(text):
    clean = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', text)
    # Anchor the known modal at the bottom; earlier session output is expected.
    # Do not strip Markdown quote markers, or quoted instructions become UI.
    lines = [line.strip().removeprefix('❯').strip() for line in clean.splitlines() if line.strip()][-15:]
    title = 'Try the new fullscreen renderer?'
    if title not in lines:
        return False
    start = len(lines)-1-lines[::-1].index(title)
    if start and (lines[start-1].endswith(':') or lines[start-1].startswith(('>', '```'))):
        return False
    block = lines[start:]
    footers = {'Enter to confirm · Esc to cancel', 'Enter to confirm · Escape to cancel'}
    allowed = {title, '1. Yes', '1. Yes, try it', '2. Not now', *footers,
               '· Flicker-free output — fixes the flashing you see during long responses',
               '· Mouse support — click to move your cursor or expand results',
               '· Selected text auto-copies to your clipboard'}
    return (block[-1] in footers and set(block) <= allowed
            and '2. Not now' in block and bool({'1. Yes', '1. Yes, try it'} & set(block)))


def dismiss_optional_renderer(name):
    r = detect._run([detect._tmux_bin(), 'capture-pane', '-p', '-t', name])
    if not r or r.returncode != 0 or not optional_renderer_dialog(r.stdout):
        return False
    # Only the exact, fully recognized optional feature dialog has a safe decline.
    sent = detect._run([detect._tmux_bin(), 'send-keys', '-t', name, '2', 'Enter'])
    return bool(sent and sent.returncode == 0)
