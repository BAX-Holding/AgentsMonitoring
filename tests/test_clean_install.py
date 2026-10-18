import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from agentsmon import __version__


class CleanInstall(unittest.TestCase):
    def test_install_without_controlling_terminal_finishes_successfully(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            env={'HOME':tmp,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.defpath,
                 'AGENTSMON_STATE':str(Path(tmp)/'state'),'AGENTSMON_CONFIG':str(Path(tmp)/'config.json')}
            # setsid: even a developer running this test from a terminal cannot supply /dev/tty.
            probe=subprocess.run(['sh','-c','{ : </dev/tty; } 2>/dev/null'],
                                 stdin=subprocess.DEVNULL,start_new_session=True,capture_output=True)
            self.assertNotEqual(probe.returncode,0,'Fixture unexpectedly has a controlling terminal')
            run=subprocess.run(['bash',str(root/'install.sh'),'--no-pip'],cwd=root,env=env,
                               stdin=subprocess.DEVNULL,start_new_session=True,capture_output=True,
                               text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('Finish setup with: agentsmon setup',run.stdout)
            self.assertNotIn('/dev/tty:',run.stderr)
            self.assertFalse((Path(tmp)/'config.json').exists(),'Setup must not run without a terminal')
            self.assertTrue((Path(tmp)/'.local/bin/agentsmon').is_file())

    def test_clean_home_installer_and_real_dashboard_without_plugins(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            env={'HOME':tmp,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.defpath,'LANG':'en_US.UTF-8',
                 'AGENTSMON_STATE':str(home/'state'),'AGENTSMON_CONFIG':str(home/'config.json'),
                 'PYTHONDONTWRITEBYTECODE':'1'}
            # No inherited auth/config/TMUX, no wizard, pip, service or boot registration.
            run=subprocess.run(['bash',str(root/'install.sh'),'--no-setup','--no-pip'],
                               cwd=root,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr)
            cli=home/'.local/bin/agentsmon'
            self.assertTrue(cli.is_file())
            version=subprocess.check_output([str(cli),'--version'],env=env,text=True,timeout=10)
            self.assertIn(__version__,version)
            (home/'config.json').write_text(json.dumps({'tmux_bin':'/nonexistent-tmux',
                'services':[],'agents':[],'daemons':[],'pinned_daemons':[],
                'modules_dir':str(home/'modules'),'keepalive':{'enabled':False}}))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            proc=subprocess.Popen([str(cli),'dashboard','--host','127.0.0.1','--port',str(port)],
                                  env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                data=None; deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state',timeout=2) as r: data=json.load(r)
                        break
                    except OSError: time.sleep(.1)
                self.assertIsNotNone(data,'Clean HOME dashboard failed to start')
                self.assertEqual(data['agent_tables'],[]); self.assertEqual(data['plugin_errors'],[])
                self.assertEqual(data['core']['state'],'clean')
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=2) as r:
                    self.assertIn('Persistent',r.read().decode())
            finally:
                proc.terminate()
                try: proc.wait(5)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()
