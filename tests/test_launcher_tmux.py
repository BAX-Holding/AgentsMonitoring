"""Launcher bootstrap runs in the shell, before either Python entry point."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import config, service


class LauncherTmuxTests(unittest.TestCase):
    def test_server_bootstrap_precedes_dashboard_and_keepalive(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(config, 'state_dir', return_value=Path(tmp)), \
                patch.object(config, 'load', return_value={}):
            source = service._launcher_content()
        bootstrap = r'tmux start-server \; set -g exit-empty off >/dev/null 2>&1 || true'
        self.assertIn(bootstrap, source)
        self.assertLess(source.index(bootstrap), source.index('nohup "$PY"'))
        self.assertLess(source.index(bootstrap), source.index('"$PY" -m agentsmon keepalive'))
        self.assertIn('TCC', source)

    def run_launcher(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bindir = home / '.local/bin'
            bindir.mkdir(parents=True)
            trace = home / 'trace'
            # Never run a real tmux binary or touch an existing server in tests.
            tmux = bindir / 'tmux'
            tmux.write_text('#!/bin/sh\nprintf "tmux\\n" >> "$TRACE"\n'
                            'printf "%s\\n" "$@" >> "$TRACE"\n'
                            'echo fixture-error >&2\nexit "${TMUX_RC:-0}"\n')
            tmux.chmod(0o755)
            python = home / 'python-stub'
            python.write_text('#!/bin/sh\nprintf "python:%s\\n" "$*" >> "$TRACE"\n')
            python.chmod(0o755)
            pgrep = bindir / 'pgrep'
            pgrep.write_text('#!/bin/sh\nexit 0\n')
            pgrep.chmod(0o755)
            cfg = home / 'config.json'
            values = {'keepalive': {'enabled': False}}
            if mode == 'custom':
                custom = home / 'tmux custom; false'
                tmux.rename(custom)
                values['tmux_bin'] = str(custom)
            elif mode == 'missing':
                values['tmux_bin'] = str(home / 'missing-tmux')
            cfg.write_text(json.dumps(values))
            env = {**os.environ, 'HOME': str(home), 'TRACE': str(trace),
                   'AGENTSMON_STATE': str(home / 'state'),
                   'TMUX_RC': '1' if mode == 'failure' else '0'}
            with patch.dict(os.environ, env), patch.object(config, 'DEFAULT_PATH', cfg), \
                    patch.object(service, '_python', return_value=str(python)):
                launcher = service._write_launcher()
                source = launcher.read_text()
                if mode == 'custom':
                    self.assertIn(shlex.quote(values['tmux_bin']) + ' start-server', source)
                syntax = subprocess.run(['/bin/sh', '-n', str(launcher)], capture_output=True,
                                        text=True, timeout=5)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                result = subprocess.run(['/bin/sh', str(launcher)], env=env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual(result.stdout, '')
                self.assertFalse(service.refresh_launcher(), 'Launcher must remain idempotent')
            self.assertEqual(trace.read_text().splitlines(),
                             ([] if mode == 'missing' else
                              ['tmux', 'start-server', ';', 'set', '-g', 'exit-empty', 'off'])
                             + ['python:-m agentsmon keepalive'])

    def test_default_tmux_is_run_before_python(self):
        self.run_launcher('default')

    def test_custom_binary_path_is_shell_quoted(self):
        self.run_launcher('custom')

    def test_missing_tmux_is_silent_and_does_not_block_python(self):
        self.run_launcher('missing')

    def test_failed_tmux_is_silent_and_does_not_block_python(self):
        self.run_launcher('failure')


if __name__ == '__main__':
    unittest.main()
