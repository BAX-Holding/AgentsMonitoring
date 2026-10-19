from argparse import Namespace
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import bridges, config, detect, probe


class BridgeRegistration(unittest.TestCase):
    def test_two_configs_are_independent_and_registration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d, patch.object(config,'state_dir',return_value=Path(d)):
            cfg = {'daemons':[{'name':'Telegram Bridge','pattern':'agent2telegram run'}],
                   'services':[{'name':'Telegram Bridge Status'}]}
            first = bridges.entry('/tmp/one.json', '/venv/bin/python', '/source path', '/tmp/state-one')
            second = bridges.entry('/tmp/two.json', '/venv/bin/python')
            for item in (first, second, first):
                bridges.register(cfg, item)
            self.assertEqual(len(cfg['daemons']), 2)
            self.assertEqual(len(cfg['services']), 2)
            with patch.object(bridges,'processes',return_value=[(123, {'config':'/tmp/one.json'})]):
                status = detect.daemon_status(cfg['daemons'])
                self.assertEqual([r['up'] for r in status], [True, False])
                with patch.object(probe.db,'record') as record:
                    probe.probe_once(cfg)
                self.assertEqual([c.args[1] for c in record.call_args_list], [True, False])
            args = shlex.split(first['restart'])
            self.assertIn('PYTHONPATH=/source path', args)
            self.assertIn('AGENT2TELEGRAM_STATE=/tmp/state-one', args)
            self.assertIn('/tmp/one.json', args)

    def test_public_cli_preserves_existing_config_and_disabled_state(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root/'config.json'
            path.write_text('{"custom":"preserve","modules_dir":""}')
            args = Namespace(bridge_config='/tmp/one.json', bridge_python='/venv/bin/python',
                             bridge_pythonpath='', bridge_state='/tmp/state')
            with patch.object(config,'DEFAULT_PATH',path), patch.object(config,'state_dir',return_value=root), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(bridges.add_noninteractive(args), 0)
                cfg = json.loads(path.read_text())
                cfg['daemons'][0]['enabled'] = False
                config.save(cfg)
                self.assertEqual(bridges.add_noninteractive(args), 0)
            cfg = json.loads(path.read_text())
            self.assertEqual(len(cfg['daemons']), 1)
            self.assertFalse(cfg['daemons'][0]['enabled'])
            self.assertEqual(cfg['custom'], 'preserve')

    def test_repeat_registration_preserves_operator_restart(self):
        cfg = {'daemons':[{'name':'Operator bridge one',
                           'pattern':'old pattern',
                           'bridge_config':'/tmp/one.json',
                           'enabled':False,
                           'restart':'OPERATOR-CONTROLLED-RESTART'}]}
        item = bridges.entry('/tmp/one.json', '/venv/bin/python')

        bridges.register(cfg, item)

        daemon = cfg['daemons'][0]
        self.assertFalse(daemon['enabled'])
        self.assertEqual(daemon['name'], 'Operator bridge one')
        self.assertEqual(daemon['restart'], 'OPERATOR-CONTROLLED-RESTART')

    def test_default_explicit_and_env_config_are_distinct(self):
        with tempfile.TemporaryDirectory() as d, patch.object(Path,'home',return_value=Path(d)), \
             patch.object(bridges,'process_env',return_value={}):
            default = bridges.process_info(123, '/venv/bin/python -m agent2telegram run')
            custom = bridges.process_info(456, '/venv/bin/python -m agent2telegram run --config /tmp/second.json')
            shell = bridges.process_info(789, 'sh -c "python -m agent2telegram run"')
        self.assertTrue(default['config'].endswith('/.config/agent2telegram/config.json'))
        self.assertEqual(custom['config'], '/tmp/second.json')
        self.assertIsNone(shell)
        raw = b'AGENT2TELEGRAM_CONFIG=/tmp/third.json\0PYTHONPATH=/src\0SECRET=never-copy\0'
        with patch.object(Path,'read_bytes',return_value=raw):
            third = bridges.process_info(333, '/venv/bin/python -m agent2telegram run')
        self.assertEqual(third['config'], '/tmp/third.json')
        self.assertNotIn('never-copy', json.dumps(third))

    def test_unreadable_env_is_not_guessed_as_default_bridge(self):
        with patch.object(bridges,'process_env',return_value=None):
            self.assertIsNone(bridges.process_info(123,'/venv/bin/python -m agent2telegram run'))

    def test_mac_restart_fields_exclude_credentials(self):
        from subprocess import CompletedProcess
        raw = '/venv/bin/python -m agent2telegram run PYTHONPATH=/source path AGENT2TELEGRAM_CONFIG=/tmp/a.json SECRET=never-copy'
        with patch.object(bridges.sys,'platform','darwin'), patch.object(Path,'read_bytes',side_effect=OSError), \
             patch.object(detect,'_run',return_value=CompletedProcess([],0,raw,'')):
            env = bridges.process_env(123)
        self.assertEqual(env, {'PYTHONPATH':'/source path','AGENT2TELEGRAM_CONFIG':'/tmp/a.json'})
