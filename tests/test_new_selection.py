from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import wizard


class NewSelection(unittest.TestCase):
    def test_missing_claude_keeps_number_one_and_invalid_inputs_reprompt(self):
        output = io.StringIO()
        bins = {'codex': '/bin/codex', 'agy': '/bin/agy'}
        with patch.object(wizard.shutil, 'which', side_effect=bins.get), \
             patch.object(os, 'access', return_value=False), \
             patch('builtins.input', side_effect=['', '99', '1', '2']), redirect_stdout(output):
            chosen = wizard.choose_agent()
        self.assertEqual(chosen['kind'], 'codex')
        self.assertIn('[1] Claude Code (not installed / not on PATH)', output.getvalue())
        self.assertIn('[2] Codex', output.getvalue())
        self.assertIn('new terminal', output.getvalue())

    def test_single_installed_cli_is_the_enter_default(self):
        with patch.object(wizard.shutil, 'which', side_effect=lambda n:'/bin/codex' if n=='codex' else None), \
             patch.object(os, 'access', return_value=False), \
             patch('builtins.input', return_value='') as ask, redirect_stdout(io.StringIO()):
            chosen = wizard.choose_agent()
        self.assertEqual(chosen['kind'], 'codex')
        self.assertIn('[2]', ask.call_args.args[0])

    def test_eof_cancels_without_selecting_an_agent(self):
        with patch('builtins.input', side_effect=EOFError), redirect_stdout(io.StringIO()):
            self.assertIsNone(wizard.choose_agent())

    def test_common_bin_paths_work_without_path(self):
        with tempfile.TemporaryDirectory() as d, patch.object(Path,'home',return_value=Path(d)), \
             patch.object(wizard.shutil,'which',return_value=None):
            path = Path(d)/'.local/bin/claude'
            path.parent.mkdir(parents=True)
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
            self.assertEqual(wizard.find_cli('claude'), str(path))

    def test_configured_disabled_name_is_already_taken(self):
        cfg = {'agents':[{'name':'Writer','enabled':False}], 'daemons':[{'name':'Worker'}]}
        self.assertTrue(wizard.name_taken('Writer', cfg, []))
        self.assertTrue(wizard.name_taken('Worker', cfg, []))
        self.assertFalse(wizard.name_taken('Other', cfg, []))


class SupportedAgentTypes(unittest.TestCase):
    def test_new_offers_only_supported_agent_clis(self):
        from agentsmon import detect, wizard
        self.assertEqual([a['kind'] for a in wizard.AGENT_TYPES], ['claude-code', 'codex', 'antigravity'])
        self.assertEqual([k for k, _, _ in detect.KNOWN_AGENTS], ['claude-code', 'codex', 'antigravity'])


class FirstMessage(unittest.TestCase):
    def test_enter_is_sent_separately_after_the_text(self):
        calls = []
        with patch.object(wizard.subprocess, 'run', side_effect=lambda argv, **kw: calls.append(argv)), \
             patch.object(wizard.time, 'sleep') as pause:
            wizard.send_first_message('Helper', 'Hello!')
        self.assertEqual(calls, [['tmux', 'send-keys', '-t', 'Helper', '-l', 'Hello!'],
                                 ['tmux', 'send-keys', '-t', 'Helper', 'Enter']])
        pause.assert_called_once()
