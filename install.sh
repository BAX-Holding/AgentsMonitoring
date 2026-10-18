#!/usr/bin/env bash
# Agents Monitoring one-command installer.
# Usage:  curl -fsSL <raw-url>/install.sh | bash      (or run it from a clone)
# Parse the entire installer before git pull can replace this very file.
main() {
set -euo pipefail
NO_SETUP=0
NO_PIP=0
for arg in "$@"; do
  case "$arg" in
    --no-setup) NO_SETUP=1 ;;
    --no-pip) NO_PIP=1 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
cd "$PWD" 2>/dev/null || cd "$HOME" 2>/dev/null || cd /

REPO="https://github.com/petrludwig-collab/AgentsMonitoring.git"
say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# Where to drop the launcher: prefer a writable $HOME dir ALREADY on PATH so `agentsmon` works in
# this very terminal right away (a piped installer can't change the parent shell's PATH). Else
# ~/.local/bin, added to the rc files for new shells.
pick_bindir() {
  oldifs="$IFS"; IFS=:
  for d in $PATH; do
    case "$d" in
      "$HOME"/*) if [ -d "$d" ] && [ -w "$d" ]; then IFS="$oldifs"; printf '%s' "$d"; return; fi ;;
    esac
  done
  IFS="$oldifs"; printf '%s' "$HOME/.local/bin"
}

PY="$(command -v python3 || true)"
[ -n "$PY" ] || err "python3 not found. Install Python 3.10+ first."
"$PY" - <<'PYEOF' || err "Python 3.10+ required."
import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)
PYEOF
say "Using $("$PY" --version)"
command -v tmux >/dev/null || say "note: tmux not found — agents run in tmux, install it before setup."

# Get the code (clone unless already inside it).
if [ -f pyproject.toml ] && grep -q "agents-monitoring" pyproject.toml 2>/dev/null &&
   [ ! -e .agentsmon-archive-install ] && [ ! -L .agentsmon-archive-install ] &&
   { [ "$(pwd -P)" != "$(cd "$HOME" && pwd -P)/.agentsmon-src" ] || [ -e .git ]; }; then
  SRC="$(pwd)"; say "Installing from current directory"
else
  SRC="${HOME}/.agentsmon-src"
  # Re-running from inside our archive must refresh it too, not reinstall old code.
  if [ -f .agentsmon-archive-install ]; then SRC="$(pwd -P)"; fi
  cd "$HOME"
  # git first — a real clone keeps `agentsmon update` working. But git over HTTPS can be
  # refused where plain HTTPS is fine: from a datacentre IP that GitHub rate-limits for
  # anonymous git, a PUBLIC repo answers 401 and git stops to ask for a password. On a fresh
  # server that is the user's first impression of the tool, and an installer must never block
  # on a prompt, so fall back to the source archive.
  is_archive_install() {
    [ -d "$SRC" ] && [ ! -L "$SRC" ] || return 1
    [ ! -e "$SRC/.git" ] && [ ! -L "$SRC/.git" ] || return 1
    if [ -e "$SRC/.agentsmon-archive-install" ] || [ -L "$SRC/.agentsmon-archive-install" ]; then
      [ -f "$SRC/.agentsmon-archive-install" ] && [ ! -L "$SRC/.agentsmon-archive-install" ] &&
        [ "$(cat "$SRC/.agentsmon-archive-install")" = agentsmon-archive-v1 ]
    else
      # Old installers wrote no marker. Recognise only their default, intact
      # source tree; never infer ownership of arbitrary folders or symlinks.
      [ "$SRC" = "${HOME}/.agentsmon-src" ] &&
        [ -f "$SRC/pyproject.toml" ] && [ -f "$SRC/agentsmon/__init__.py" ] &&
        grep -q 'agents-monitoring' "$SRC/pyproject.toml" || return 1
      links="$(find "$SRC" -type l -print -quit)" || return 1
      [ -z "$links" ]
    fi
  }
  fetch_tarball() (
    say "Fetching the source archive (no git)"
    # Same filesystem: prepare completely before touching the current installation.
    tmp="$(mktemp -d "${SRC}.stage.XXXXXX")" || return 1
    published=0
    cleanup_archive() {
      if [ "$published" -eq 0 ] && [ -d "$tmp/previous" ]; then
        if [ -e "$SRC" ] || [ -L "$SRC" ] || ! mv "$tmp/previous" "$SRC"; then
          printf 'Could not restore %s; previous files preserved in %s/previous.\n' "$SRC" "$tmp" >&2
          return
        fi
      fi
      rm -rf "$tmp"
    }
    trap cleanup_archive EXIT
    trap 'exit 1' HUP INT TERM
    url="https://codeload.github.com/petrludwig-collab/AgentsMonitoring/tar.gz/refs/heads/main"
    curl -fsSL --retry 2 "$url" -o "$tmp/src.tgz" || return 1
    tar xzf "$tmp/src.tgz" -C "$tmp" || return 1
    dir="$(find "$tmp" -maxdepth 1 -type d -name 'AgentsMonitoring-*' | head -1)"
    [ -n "$dir" ] || return 1
    [ -f "$dir/agentsmon/__init__.py" ] &&
      grep -q 'agents-monitoring' "$dir/pyproject.toml" || return 1
    printf 'agentsmon-archive-v1\n' > "$dir/.agentsmon-archive-install" || return 1
    if [ -e "$SRC" ] || [ -L "$SRC" ]; then
      is_archive_install || return 1
      mv "$SRC" "$tmp/previous" || return 1
    fi
    mv "$dir" "$SRC" || return 1
    published=1
    say "Installed from archive — 'agentsmon update' will ask you to re-run this installer."
  )
  if [ -d "$SRC/.git" ]; then
    say "Updating $SRC"
    # A failed update may mean local work or a divergent branch. Never replace it
    # with an archive: preserve the checkout and let its owner resolve the error.
    updated=0
    for n in 1 2 3; do
      if GIT_TERMINAL_PROMPT=0 git -C "$SRC" pull --ff-only; then updated=1; break; fi
      [ "$n" -eq 3 ] || { say "Update refused, retrying ($((n+1))/3)"; sleep 2; }
    done
    [ "$updated" -eq 1 ] || err "Could not update $SRC after 3 attempts; existing files preserved. Check the git error and re-run this installer to try again."
  elif is_archive_install; then
    fetch_tarball || err "Could not update the archive; previous files preserved. Re-run this installer to try again."
  elif [ -e "$SRC" ] || [ -L "$SRC" ]; then
    err "$SRC already exists without a git checkout; files preserved. Back it up and move it aside before a fresh install."
  elif command -v git >/dev/null 2>&1; then
    say "Cloning into $SRC"
    # GitHub answers 401 to anonymous git from datacentre IPs intermittently — the very next
    # attempt usually succeeds (Hermes' own installer recovers the same way, on try 2 of 4).
    # Retry before giving up on git, because a real clone is what keeps `update` working;
    # the tarball is the last resort, not the second choice.
    n=1
    while [ "$n" -le 3 ]; do
      GIT_TERMINAL_PROMPT=0 git clone --depth 1 "$REPO" "$SRC" 2>/dev/null && break
      rm -rf "$SRC"
      n=$((n+1))
      [ "$n" -le 3 ] && { say "Clone refused, retrying ($n/3)"; sleep 2; }
    done
    [ -d "$SRC/.git" ] || fetch_tarball || err "Could not fetch the project."
  else
    fetch_tarball || err "Could not fetch the project (no git, and the archive download failed)."
  fi
fi

# pip is OPTIONAL — the package is pure standard library. Try pip (so hooks/other tools can
# import it), but EITHER WAY drop our own launcher into a dir on PATH so `agentsmon` is a real
# command right after install — no PYTHONPATH to remember, no new shell when a PATH dir is writable.
if [ "$NO_PIP" -eq 0 ] && { "$PY" -m pip --version >/dev/null 2>&1 || "$PY" -m ensurepip --upgrade >/dev/null 2>&1; }; then
  "$PY" -m pip install --user --upgrade "$SRC" >/dev/null 2>&1 \
    || "$PY" -m pip install --user --break-system-packages --upgrade "$SRC" >/dev/null 2>&1 || true
fi
BIND="$(pick_bindir)"
mkdir -p "$BIND"
printf '#!/bin/sh\nexec env PYTHONPATH="%s" "%s" -m agentsmon "$@"\n' "$SRC" "$PY" > "$BIND/agentsmon"
chmod +x "$BIND/agentsmon"
RUN=("$BIND/agentsmon"); HOW="agentsmon"
case ":$PATH:" in
  *":$BIND:"*)
    say "Installed launcher in $BIND (already on PATH) — 'agentsmon' works now." ;;
  *)
    say "Installed launcher in $BIND — adding it to PATH for new shells."
    for rc in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
      [ -e "$rc" ] || continue
      grep -qs "$BIND" "$rc" || echo "export PATH=\"$BIND:\$PATH\"" >> "$rc"
    done
    grep -qs "$BIND" "$HOME/.bashrc" 2>/dev/null || echo "export PATH=\"$BIND:\$PATH\"" >> "$HOME/.bashrc"
    export PATH="$BIND:$PATH"
    say "For THIS terminal, run:  export PATH=\"$BIND:\$PATH\"   (new terminals get it automatically)" ;;
esac

say "Run it later with:  $HOW status   (add more bots anytime with:  $HOW add)"
if [ "$NO_SETUP" -eq 0 ] && { : </dev/tty; } 2>/dev/null; then
  say "Starting setup…"; exec "${RUN[@]}" setup </dev/tty
else say "Installed. Finish setup with: $HOW setup"; fi
}
# Keep the exit on this parsed line: never resume reading a replaced script tail.
main "$@"; exit
