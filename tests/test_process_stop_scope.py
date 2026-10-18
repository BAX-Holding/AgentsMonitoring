"""Uninstall and daemon Stop must not target other users or command-line bystanders.

All signalling, cron and pip calls are intercepted. Regex matching uses grep -E on
synthetic command lines (the same POSIX ERE dialect as pkill), never live processes.
"""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import config, dashboard, service, uninstaller


class ProcessStopScope(unittest.TestCase):
    def uninstall_calls(self):
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv,0,b'',b'')
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            with patch.object(Path,'home',return_value=home), \
                 patch.object(config,'DEFAULT_PATH',home/'config'/'config.json'), \
                 patch.object(service,'uninstall_cron',side_effect=lambda:calls.append('remove-cron')), \
                 patch.object(service,'stop_dashboard',side_effect=lambda:calls.append('stop-dashboard')), \
                 patch.object(uninstaller.shutil,'which',return_value='/fixture/pkill'), \
                 patch.object(uninstaller.shutil,'rmtree') as remove, \
                 patch.object(uninstaller.subprocess,'run',side_effect=run), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(uninstaller.run(yes=True),0)
                remove.assert_not_called()  # No fixture directories to remove.
        return calls

    def test_uninstall_uses_pid_aware_dashboard_stop(self):
        calls=self.uninstall_calls()
        self.assertIn('stop-dashboard',calls)
        self.assertLess(calls.index('remove-cron'),calls.index('stop-dashboard'))
        self.assertFalse(any(isinstance(c,list) and c[0]=='pkill' and 'dashboard' in c[-1]
                             for c in calls),calls)

    def test_uninstall_keepalive_is_uid_scoped_and_matches_only_the_runner(self):
        calls=self.uninstall_calls()
        kills=[c for c in calls if isinstance(c,list) and c[0]=='pkill']
        self.assertEqual(len(kills),1,kills)
        argv=kills[0]
        self.assertEqual(argv[:-1],['pkill','-u',str(os.getuid()),'-f','--'])
        pattern=argv[-1]
        positive=(
            '/usr/bin/python3 -m agentsmon keepalive',
            '/opt/venv/bin/python3.12 -m agentsmon keepalive --loop',
            'python -m agentsmon keepalive --loop',
            '/opt/venv/bin/python /opt/venv/bin/agentsmon keepalive --loop',
        )
        negative=(
            'sh -c echo agentsmon dashboard; sleep 30',
            'sh -c echo agentsmon keepalive; sleep 30',
            'sh -c echo python -m agentsmon keepalive',
            '/usr/bin/python3 -c print("-m agentsmon keepalive")',
            '/usr/bin/python3 -m agentsmon keepalive-other',
            '/usr/bin/python3 -m agentsmon dashboard',
        )
        for line in positive+negative:
            with self.subTest(command=line):
                result=subprocess.run(['grep','-E','--',pattern],input=line+'\n',
                                      capture_output=True,text=True,timeout=5)
                self.assertIn(result.returncode,(0,1),result.stderr)
                self.assertEqual(result.returncode==0,line in positive)

    def test_daemon_stop_is_uid_scoped_and_disables_before_signalling(self):
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv,1 if argv[0]=='pgrep' else 0,'','')
        cfg={'agents':[],'daemons':[{'name':'Example','pattern':'-example-worker'}]}
        with patch.object(config,'load',return_value=cfg), \
             patch('agentsmon.managed.discover',return_value=None), \
             patch.object(dashboard,'_set_enabled',side_effect=lambda *args:calls.append(args)), \
             patch.object(dashboard.subprocess,'run',side_effect=run):
            ok,message=dashboard._agent_action('Example','stop')
        self.assertTrue(ok,message)
        self.assertEqual(calls,[('Example',False),
            ['pkill','-u',str(os.getuid()),'-f','--','-example-worker'],
            ['pgrep','-u',str(os.getuid()),'-f','--','-example-worker']])

    def test_cancelled_uninstall_does_not_stop_or_remove_anything(self):
        with patch('builtins.input',return_value='n'), \
             patch.object(service,'uninstall_cron') as cron, \
             patch.object(service,'stop_dashboard') as stop, \
             patch.object(uninstaller.subprocess,'run') as run, \
             patch.object(uninstaller.shutil,'rmtree') as remove, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(uninstaller.run(),0)
        for action in (cron,stop,run,remove): action.assert_not_called()
