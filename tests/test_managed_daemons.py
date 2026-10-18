"""Daemon actions must cooperate with the owning user service manager."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from agentsmon import config, dashboard


class ManagedDaemons(unittest.TestCase):
    def action(self, owner, action, running_after):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            output = ''
            rc = 0
            if 'show' in argv:
                output = 'LoadState=loaded\nActiveState='+('active' if running_after else 'inactive')+'\n'
            if 'print' in argv:
                output = 'state = running\npid = 123\n' if running_after else ''
                rc = 0 if running_after else 113
            return subprocess.CompletedProcess(argv, rc, output, '')
        spec = {'name':'Example', 'pattern':'example-worker', 'manager':owner,
                'restart':'NEVER RUN THE STANDALONE COMMAND'}
        with patch.object(config, 'load', return_value={'daemons':[spec]}), \
             patch.object(dashboard, '_set_enabled'), \
             patch.object(subprocess, 'run', side_effect=run):
            result = dashboard._agent_action('Example', action)
        return result, calls

    def test_systemd_stop_uses_unit_and_verifies_inactive(self):
        result, calls = self.action({'type':'systemd','unit':'example.service'}, 'stop', False)
        self.assertTrue(result[0], result)
        self.assertIn(['systemctl','--user','stop','example.service'], calls)
        self.assertFalse(any(c[0]=='pkill' or isinstance(c, str) for c in calls))

    def test_systemd_stop_failure_is_not_reported_as_success(self):
        result, _ = self.action({'type':'systemd','unit':'example.service'}, 'stop', True)
        self.assertFalse(result[0])

    def test_systemd_restart_does_not_launch_a_second_daemon(self):
        result, calls = self.action({'type':'systemd','unit':'example.service'}, 'restart', True)
        self.assertTrue(result[0], result)
        self.assertIn(['systemctl','--user','restart','example.service'], calls)
        self.assertFalse(any(isinstance(c, str) for c in calls))

    def test_launchd_stop_boots_out_and_restart_kickstarts(self):
        target = f'gui/{os.getuid()}/org.example.worker'
        owner = {'type':'launchd', 'target':target}
        result, calls = self.action(owner, 'stop', False)
        self.assertTrue(result[0], result)
        self.assertIn(['launchctl','bootout',target], calls)
        result, calls = self.action(owner, 'restart', True)
        self.assertTrue(result[0], result)
        self.assertIn(['launchctl','kickstart','-k',target], calls)

    def test_su_environment_fills_missing_runtime_and_bus_without_overriding(self):
        from agentsmon.managed import user_env
        with patch.dict(os.environ, {}, clear=True), patch.object(Path,'is_dir',return_value=True):
            env = user_env()
        self.assertEqual(env['XDG_RUNTIME_DIR'], f'/run/user/{os.getuid()}')
        self.assertEqual(env['DBUS_SESSION_BUS_ADDRESS'], f'unix:path=/run/user/{os.getuid()}/bus')
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR':'/custom', 'DBUS_SESSION_BUS_ADDRESS':'custom'}, clear=True):
            self.assertEqual(user_env()['DBUS_SESSION_BUS_ADDRESS'], 'custom')

    def test_enable_now_and_linger_use_own_user_without_sudo(self):
        from agentsmon import managed
        calls = []
        def run(argv, **kw):
            calls.append((argv,kw))
            return subprocess.CompletedProcess(argv,0,'','')
        with patch.dict(os.environ,{},clear=True), patch.object(Path,'is_dir',return_value=True), \
             patch.object(subprocess,'run',side_effect=run):
            ok, notes = managed.activate({'type':'systemd','unit':'example.service'})
        self.assertTrue(ok)
        self.assertEqual(calls[0][0], ['systemctl','--user','enable','--now','example.service'])
        self.assertEqual(calls[1][0][:2], ['loginctl','enable-linger'])
        self.assertTrue(all('sudo' not in argv for argv,_ in calls))
        self.assertIn('DBUS_SESSION_BUS_ADDRESS', calls[0][1]['env'])
        self.assertEqual(len(notes),2)

    def test_linger_denial_is_visible_and_unit_start_failure_is_fatal(self):
        from agentsmon import managed
        def denied(argv):
            return subprocess.CompletedProcess(argv,1 if argv[0]=='loginctl' else 0,'','')
        with patch.object(managed,'run',side_effect=denied):
            ok, notes = managed.activate({'type':'systemd','unit':'example.service'})
        self.assertTrue(ok)
        self.assertIn('administrator', notes[-1])
        with patch.object(managed,'run',return_value=None):
            ok, notes = managed.activate({'type':'systemd','unit':'example.service'})
            self.assertFalse(ok)
            self.assertIsNone(managed.active({'type':'systemd','unit':'example.service'}))

    def test_cgroup_identifies_wrapped_user_service(self):
        from agentsmon import managed
        group = f'0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice/example.service\n'
        with patch.object(managed.sys,'platform','linux'), patch.object(managed,'process_ids',return_value=[123]), \
             patch.object(Path,'read_text',return_value=group), \
             patch.object(managed,'properties',return_value={'LoadState':'loaded'}):
            self.assertEqual(managed.discover({'name':'Example','pattern':'wrapper'}),
                             {'type':'systemd','unit':'example.service'})

    def test_service_manager_unavailable_cannot_fake_successful_stop(self):
        from agentsmon import managed
        with patch.object(managed,'run',return_value=subprocess.CompletedProcess([],0,'','')), \
             patch.object(managed.time,'sleep'):
            ok, _ = managed.action({'name':'Example','manager':{'type':'systemd','unit':'example.service'}},'stop')
        self.assertFalse(ok)

    def test_ambiguous_service_ownership_never_falls_back_to_process_kill(self):
        from agentsmon import managed
        groups = [f'0::/user.slice/user@{os.getuid()}.service/app.slice/{u}.service\n'
                  for u in ('first', 'second')]
        with patch.object(managed.sys, 'platform', 'linux'), \
             patch.object(managed, 'process_ids', return_value=[1, 2]), \
             patch.object(Path, 'read_text', side_effect=groups), \
             patch.object(managed, 'properties', return_value={'LoadState':'loaded'}), \
             patch.object(managed, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')) as run:
            ok, _ = managed.action({'name':'Example', 'pattern':'example'}, 'stop')
        self.assertFalse(ok)
        run.assert_not_called()

    def test_known_cgroup_with_unavailable_bus_retains_service_ownership(self):
        from agentsmon import managed
        group = f'0::/user.slice/user@{os.getuid()}.service/app.slice/example.service\n'
        with patch.object(managed.sys, 'platform', 'linux'), \
             patch.object(managed, 'process_ids', return_value=[1]), \
             patch.object(Path, 'read_text', return_value=group), \
             patch.object(managed, 'properties', return_value={}):
            self.assertEqual(managed.discover({'name':'Example'}),
                             {'type':'systemd', 'unit':'example.service'})
