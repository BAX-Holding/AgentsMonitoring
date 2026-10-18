"""Rapid git checkouts can have identical source sizes and integer mtimes."""
import contextlib
import io
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import config, service, updater, wizard


class UpdateBytecode(unittest.TestCase):
    def test_launcher_does_not_write_bytecode_in_a_packaged_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            package = home / 'site-packages/agentsmon'
            package.mkdir(parents=True)
            init = package / '__init__.py'
            init.write_text('__version__ = "0.3.1"\n')
            with patch.object(service.agentsmon, '__file__', str(init)), \
                    patch.object(config, 'state_dir', return_value=home), \
                    patch.object(config, 'load', return_value={}), \
                    patch.object(service, 'refresh_bytecode') as refresh:
                service._write_launcher()
            refresh.assert_not_called()

    def test_launcher_refresh_handles_update_started_by_old_loaded_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / '.git').mkdir()
            package = home / 'agentsmon'
            package.mkdir()
            init = package / '__init__.py'
            init.write_text('__version__ = "0.3.0"\n')
            py_compile.compile(str(init), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            before = init.stat()
            init.write_text('__version__ = "0.3.1"\n')
            os.utime(init, ns=(before.st_atime_ns, before.st_mtime_ns))
            with patch.object(service.agentsmon, '__file__', str(init)), \
                    patch.object(config, 'state_dir', return_value=home), \
                    patch.object(config, 'load', return_value={}):
                service._write_launcher()
            result = subprocess.run([sys.executable, '-c',
                                     'import agentsmon; print(agentsmon.__version__)'],
                                    cwd=home, env={**os.environ, 'PYTHONPATH': str(home)},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '0.3.1')

    def test_update_reloads_changed_source_even_in_same_timestamp_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            src = home / '.agentsmon-src'
            (src / '.git').mkdir(parents=True)
            package = src / 'agentsmon'
            package.mkdir()
            init = package / '__init__.py'
            init.write_text('__version__ = "0.3.0"\n')
            py_compile.compile(str(init), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            original = init.stat()
            state = home / 'state'
            state.mkdir()
            launcher = state / 'agentsmon-launch.sh'
            launcher.write_text('# fixture service')
            real_run = subprocess.run
            seen = []

            def command(argv, **kwargs):
                if argv[0] == 'git' and 'pull' in argv:
                    init.write_text('__version__ = "0.3.1"\n')
                    os.utime(init, ns=(original.st_atime_ns, original.st_mtime_ns))
                    return subprocess.CompletedProcess(argv, 0, '', '')
                if argv == ['sh', str(launcher)]:
                    result = real_run([sys.executable, '-c',
                                       'import agentsmon; print(agentsmon.__version__)'],
                                      cwd=home, env={**os.environ, 'PYTHONPATH': str(src)},
                                      capture_output=True, text=True, timeout=10)
                    seen.append(result.stdout.strip())
                    return result
                return subprocess.CompletedProcess(argv, 0, '', '')

            with patch.object(Path, 'home', return_value=home), \
                    patch.object(updater.agentsmon, '__file__', str(init)), \
                    patch.object(updater, '_head', return_value='abc123'), \
                    patch.object(updater, '_summary', return_value='fixture update'), \
                    patch.object(updater.subprocess, 'run', side_effect=command), \
                    patch.object(config, 'state_dir', return_value=state), \
                    patch.object(config, 'load', return_value={}), \
                    patch.object(wizard, 'migrate_config', return_value=False), \
                    patch.object(service, 'stop_dashboard'), \
                    patch.object(service, '_write_launcher', return_value=launcher), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(updater.run(), 0)
            self.assertEqual(seen, ['0.3.1'], 'Fresh process imported stale bytecode after update')
