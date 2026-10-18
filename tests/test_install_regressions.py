"""Offline clean-install/multi-user regressions; never touch live processes or cron."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agentsmon import config, dashboard, service, updater, wizard


class InstallationRegressions(unittest.TestCase):
    def test_launcher_ignores_foreign_dashboard_but_recognises_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); bindir=home/'.local/bin'; bindir.mkdir(parents=True)
            tmux=bindir/'tmux'
            tmux.write_text('#!/bin/sh\nexit 0\n'); tmux.chmod(0o755)
            state=home/'state'; state.mkdir()
            calls=home/'calls.jsonl'
            # The fake pgrep models a foreign user's daemon, plus optionally our own.
            pgrep=bindir/'pgrep'
            pgrep.write_text(f'#!{sys.executable}\n'+r'''
import json, os, sys
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(['pgrep']+sys.argv[1:])+'\n')
scoped = '-u' in sys.argv and sys.argv[sys.argv.index('-u')+1] == str(os.getuid())
sys.exit(1 if scoped and os.environ['OWN'] == '0' else 0)
'''); pgrep.chmod(0o755)
            runner=home/'fake-python'
            runner.write_text(f'#!{sys.executable}\n'+r'''
import json, os, sys
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\n')
'''); runner.chmod(0o755)
            with patch.object(config,'state_dir',return_value=state), \
                 patch.object(config,'DEFAULT_PATH',home/'config.json'), \
                 patch.object(service,'_python',return_value=str(runner)):
                launcher=service._write_launcher()
            for own in ('0','1'):
                with self.subTest(own_dashboard=own):
                    calls.write_text('')
                    env={**os.environ,'HOME':tmp,'CALLS':str(calls),'OWN':own}
                    run=subprocess.run(['sh',str(launcher)],env=env,capture_output=True,text=True,timeout=10)
                    self.assertEqual(run.returncode,0,run.stderr)
                    deadline=time.monotonic()+2
                    while True:
                        entries=[json.loads(x) for x in calls.read_text().splitlines()]
                        if own=='1' or ['-m','agentsmon','dashboard'] in entries or time.monotonic()>deadline:
                            break
                        time.sleep(.02)
                    self.assertIn(['-m','agentsmon','keepalive'],entries)
                    self.assertEqual(['-m','agentsmon','dashboard'] in entries,own=='0',entries)
                    self.assertIn(['pgrep','-u',str(os.getuid()),'-f','--','-m agentsmon dashboard$'],entries)

    def test_stop_fallback_only_discovers_current_users_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            def processes(argv,**kwargs):
                # An unscoped lookup includes a foreign user's PID.
                out='432101\n' if '-u' in argv and argv[argv.index('-u')+1]==str(os.getuid()) else '432101\n432102\n'
                return subprocess.CompletedProcess(argv,0,out,'')
            with patch.object(dashboard,'pidfile_path',return_value=Path(tmp)/'missing'), \
                 patch.object(service.subprocess,'run',side_effect=processes):
                self.assertEqual(service._dashboard_pids(),[432101])

    def test_updater_stops_precisely_and_refreshes_existing_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); src=home/'.agentsmon-src'; (src/'.git').mkdir(parents=True)
            state=home/'state'; state.mkdir(); launcher=state/'agentsmon-launch.sh'
            launcher.write_text('old unscoped launcher')
            events=[]
            def fake_run(argv,**kwargs):
                events.append(argv)
                return subprocess.CompletedProcess(argv,0,'','')
            def rewrite():
                events.append('rewrite'); return launcher
            with patch.object(Path,'home',return_value=home), \
                 patch.object(config,'state_dir',return_value=state), \
                 patch.object(config,'load',return_value={}), \
                 patch.object(wizard,'migrate_config',return_value=False), \
                 patch.object(updater,'_head',return_value='abc123'), \
                 patch.object(updater,'_summary',return_value='Already up to date'), \
                 patch.object(updater.subprocess,'run',side_effect=fake_run), \
                 patch.object(service,'stop_dashboard',side_effect=lambda:events.append('stop')) as stop, \
                 patch.object(service,'_write_launcher',side_effect=rewrite) as write, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(updater.run(),0)
            stop.assert_called_once_with(); write.assert_called_once_with()
            self.assertLess(events.index('stop'),events.index('rewrite'))
            self.assertLess(events.index('rewrite'),events.index(['sh',str(launcher)]))
            self.assertFalse(any(isinstance(e,list) and e[0]=='pkill' for e in events),events)

    def test_auth_error_points_to_existing_setup_command(self):
        with self.assertRaises(SystemExit) as error:
            dashboard.require_auth_or_die('0.0.0.0',{'dashboard':{}})
        self.assertIn('agentsmon setup',str(error.exception))
        self.assertNotIn('agentsmon wizard',str(error.exception))
        self.assertIn('agentsmon setup',dashboard.require_auth_or_die.__doc__)
