"""Rehearsal regressions: login gates, explicit stops, and wrapped daemons."""
import copy
import io
import subprocess
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

from agentsmon import config, dashboard, detect, managed, status, wizard


class Onboarding(unittest.TestCase):
    def test_inaccessible_proc_descriptors_do_not_crash_boot_discovery(self):
        from pathlib import Path
        for error in (PermissionError('process not inspectable'), FileNotFoundError('process exited')):
            with self.subTest(error=type(error).__name__), \
                 patch.object(Path, 'is_dir', return_value=True), \
                 patch.object(Path, 'iterdir', side_effect=error):
                self.assertEqual(detect.open_files([42]), [])

    def test_codex_login_probe_fails_closed_on_timeout(self):
        with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('codex', 10)):
            self.assertFalse(wizard.codex_is_logged_in('/fixture/codex'))

    def test_login_screen_recognition_is_anchored_and_recovers(self):
        codex = 'Welcome to Codex\n› 1. Sign in with ChatGPT\n  2. Sign in with Device Code\n  3. Provide your own API key'
        claude = '❯ Hello\n⎿ Not logged in · Please run /login'
        self.assertTrue(detect.login_screen('codex', codex))
        self.assertTrue(detect.login_screen('claude-code', claude))
        self.assertTrue(detect.login_screen('codex', codex.replace('›', '>')))
        self.assertTrue(detect.login_screen('claude-code',
            '❯ Hello! Briefly introduce yourself.\n──────────────────\n'
            '  ⏵⏵ bypass permissions on (shift+tab to cycle)     Not logged in · Run /login\n'
            '                                              ◐ medium · /effort'))
        self.assertFalse(detect.login_screen('codex', '> '+codex.replace('\n', '\n> ')))
        self.assertFalse(detect.login_screen('claude-code', '> Not logged in · Please run /login'))
        self.assertFalse(detect.login_screen('codex', codex+'\nReady\n'*20))
        self.assertFalse(detect.login_screen('claude-code', 'Working on the login page now.'))

    def test_discovery_marks_login_without_changing_liveness(self):
        screen = '1. Sign in with ChatGPT\n2. Sign in with Device Code\n3. Provide your own API key'
        def resolve(rows, *_):
            for row in rows:
                row.update(transcript=None)
        with patch.object(detect, 'tmux_sessions', return_value=[{'name':'Helper','created':1}]), \
             patch.object(detect, '_pane_pids', return_value=[42]), \
             patch.object(detect, '_proc_table', return_value=({42:'codex'}, {})), \
             patch.object(detect, '_proc_age', return_value=1), \
             patch.object(detect, '_codex_model', return_value=None), \
             patch.object(detect, '_session_cwd', return_value='/workspace'), \
             patch('agentsmon.identity.resolve', side_effect=resolve), \
             patch.object(detect, '_run', return_value=subprocess.CompletedProcess([],0,screen,'')):
            row = detect.discover_agents(now=10)[0]
        self.assertTrue(row['alive'])
        self.assertTrue(row['needs_login'])
        self.assertEqual(row['status'], 'Needs login')

    def test_unsigned_codex_gets_no_greeting_or_login_enter(self):
        for rc in (1, 0):
            with self.subTest(rc=rc), ExitStack() as stack:
                output, calls = io.StringIO(), []
                stack.enter_context(redirect_stdout(output))
                chosen = {**wizard.AGENT_TYPES[1], 'executable': '/fixture/codex'}
                stack.enter_context(patch.object(wizard, 'choose_agent', return_value=chosen))
                stack.enter_context(patch.object(wizard.shutil, 'which', return_value='/fixture/tmux'))
                stack.enter_context(patch.object(config, 'load', return_value={'agents': []}))
                stack.enter_context(patch.object(config, 'save'))
                stack.enter_context(patch.object(detect, 'tmux_sessions', return_value=[]))
                stack.enter_context(patch.object(wizard.service, 'install'))
                stack.enter_context(patch.object(wizard, 'wait_for_tui', return_value=True))
                stack.enter_context(patch('builtins.input', side_effect=['Helper', '/workspace', 'yes']))
                def run(argv, **kwargs):
                    calls.append(argv)
                    return subprocess.CompletedProcess(argv, rc if argv[1:] == ['login', 'status'] else 0, '', '')
                stack.enter_context(patch.object(subprocess, 'run', side_effect=run))
                self.assertEqual(wizard.new(), 0)
                greetings = [c for c in calls if 'Hello! Briefly introduce yourself.' in c]
                self.assertEqual(len(greetings), int(rc == 0))
                self.assertIn(['/fixture/codex', 'login', 'status'], calls)
                if rc:
                    self.assertIn('Sign in with Device Code', output.getvalue())
                    # Only the shell launch may receive Enter, never the login screen.
                    self.assertEqual(sum('send-keys' in c for c in calls), 1)

    def test_setup_preserves_explicit_stop_and_custom_fields(self):
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg['agents'] = [{'name':'Stopped', 'enabled':False, 'restart':'custom-resume', 'tag':'Custom'}]
        cfg['daemons'] = [{'name':'Hermes', 'enabled':False, 'pattern':'custom', 'restart':'custom-start'}]
        cfg['pinned_daemons'] = [{'name':'Hermes', 'tag':'Custom gateway'}]
        candidate = {'kind':'daemon', 'obj':wizard.COMMON_DAEMONS[1], 'display':'Hermes'}
        with patch.object(config, 'load', return_value=copy.deepcopy(cfg)), \
             patch.object(config, 'save') as save, \
             patch.object(wizard, '_scan_candidates', return_value=[candidate]), \
             patch.object(wizard.shutil, 'which', return_value='/fixture/tmux'), \
             patch.object(managed, 'discover', return_value={'type':'systemd','unit':'hermes-gateway.service'}), \
             patch.object(managed, 'activate', return_value=(True, [])) as activate, \
             patch.object(detect, 'daemon_telegram_bot', return_value=''), \
             patch('builtins.input', side_effect=['all', 'n', '8765', 'n', 'n']), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(wizard.run(), 0)
        got = save.call_args.args[0]
        self.assertEqual(got['agents'], cfg['agents'])
        self.assertFalse(got['daemons'][0]['enabled'])
        self.assertEqual(got['daemons'][0]['restart'], 'custom-start')
        self.assertEqual(got['pinned_daemons'][0]['tag'], 'Custom gateway')
        activate.assert_not_called()

    def test_scan_uses_service_owner_for_wrapped_gateway(self):
        with patch.object(detect, 'discover_agents', return_value=[]), \
             patch.object(wizard, 'COMMON_DAEMONS', [wizard.COMMON_DAEMONS[1]]), \
             patch.object(wizard, '_running', return_value=False), \
             patch.object(managed, 'discover', return_value={'type':'systemd','unit':'hermes-gateway.service'}), \
             patch.object(managed, 'active', return_value=True), \
             patch.object(managed, 'process_ids', return_value=[]), \
             patch('agentsmon.bridges.candidates', return_value=[]):
            rows = wizard._scan_candidates(set())
        self.assertEqual(len(rows), 1)
        self.assertNotIn('not running', rows[0]['display'])

    def test_add_does_not_offer_disabled_unit_as_repair(self):
        cfg = {'daemons':[{'name':'Hermes','enabled':False}]}
        with patch.object(config.DEFAULT_PATH.__class__, 'exists', return_value=True), \
             patch.object(config, 'load', return_value=cfg), \
             patch.object(wizard, '_scan_candidates', return_value=[]), \
             patch.object(managed, 'discover') as discover, redirect_stdout(io.StringIO()):
            self.assertEqual(wizard.add(), 0)
        discover.assert_not_called()

    def test_missing_stopped_agent_stays_visible_in_terminal_and_dashboard(self):
        cfg = {'agents':[{'name':'Stopped', 'kind':'codex', 'enabled':False}], 'daemons':[]}
        with patch.object(detect, 'discover_agents', return_value=[]), \
             patch.object(detect, 'telegram_links', return_value={}), \
             patch.object(status, '_dashboard_lines', return_value=[]):
            terminal = status.render(cfg)
            rows = dashboard._agents_state(cfg)
        self.assertIn('Stopped', terminal)
        self.assertIn('stopped', terminal.lower())
        self.assertEqual(rows[0]['status'], 'Stopped (manual)')
        self.assertFalse(rows[0]['alive'])

    def test_login_screen_is_visible_without_marking_process_dead(self):
        row = {'name':'Helper', 'kind':'codex', 'label':'Codex', 'session_id':None,
               'alive':True, 'age':1, 'needs_login':True, 'status':'Needs login'}
        with patch.object(detect, 'discover_agents', return_value=[row]), \
             patch.object(status, '_dashboard_lines', return_value=[]):
            out = status.render({'agents':[{'name':'Helper'}]})
        self.assertIn('🟡', out)
        self.assertNotIn('🟢', out)
        self.assertIn('Needs login', out)


if __name__ == '__main__':
    unittest.main()
