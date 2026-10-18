"""Session identity must belong to a process, never just to its working directory."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import detect, wizard


class SessionOwnership(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.home = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(Path, 'home', return_value=self.home))
        self.stack.enter_context(patch.dict(os.environ, {'CODEX_HOME':str(self.home/'.codex')}))
        self.now = 1_800_000_000
        self.ids = ['11111111-1111-4111-8111-111111111111',
                    '22222222-2222-4222-8222-222222222222']
        self.commands = {101: 'codex', 201: 'codex'}
        self.ages = {101: 300, 201: 100}
        self.stack.enter_context(patch.object(detect.time, 'time', return_value=self.now))
        self.stack.enter_context(patch.object(detect, 'tmux_sessions', return_value=[
            {'name': 'First', 'created': self.now-500}, {'name': 'Second', 'created': self.now-400}]))
        self.stack.enter_context(patch.object(detect, '_proc_table', return_value=(self.commands, {})))
        self.stack.enter_context(patch.object(detect, '_pane_pids', side_effect=lambda n: [101 if n=='First' else 201]))
        self.stack.enter_context(patch.object(detect, '_session_cwd', return_value='/work/shared'))
        self.stack.enter_context(patch.object(detect, '_proc_age', side_effect=lambda p: self.ages[p]))
        self.stack.enter_context(patch.object(detect, 'open_files', return_value=[]))

    def rollout(self, sid, age, kind='codex'):
        stamp = datetime.fromtimestamp(self.now-age, timezone.utc).isoformat()
        if kind == 'codex':
            path = self.home/'.codex/sessions'/f'rollout-{sid}.jsonl'
            record = {'type':'session_meta','timestamp':stamp,
                      'payload':{'id':sid,'cwd':'/work/shared','timestamp':stamp}}
        else:
            path = self.home/'.claude/projects/-work-shared'/f'{sid}.jsonl'
            record = {'type':'user','timestamp':stamp,'sessionId':sid,'cwd':'/work/shared'}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record)+'\n')
        os.utime(path, (self.now-age, self.now-age))
        return path

    def test_two_codex_processes_same_cwd_keep_their_own_ids(self):
        self.rollout(self.ids[0], 299)
        self.rollout(self.ids[1], 99)
        rows = detect.discover_agents()
        self.assertEqual([r['session_id'] for r in rows], self.ids)
        self.assertIn(self.ids[0], rows[0]['resume_cmd'])

    def test_ambiguous_same_start_time_has_no_resume(self):
        self.ages[201] = 300
        self.rollout(self.ids[0], 299)
        self.rollout(self.ids[1], 298)
        for row in detect.discover_agents():
            self.assertIsNone(row['session_id'])
            self.assertIsNone(row['resume_cmd'])

    def test_old_rollout_is_not_owned_by_new_process(self):
        self.rollout(self.ids[0], 1000)
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], [None, None])

    def test_two_claude_processes_same_cwd_not_assigned_by_scan_order(self):
        self.commands.update({101:'claude', 201:'claude'})
        self.rollout(self.ids[0], 299, 'claude')
        self.rollout(self.ids[1], 99, 'claude')
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], self.ids)

    def test_uuid_in_unrelated_argument_is_not_a_resume_id(self):
        self.commands[101] = f'codex --cd /work/{self.ids[0]}'
        self.assertIsNone(detect.discover_agents()[0]['session_id'])

    def test_explicit_resume_is_preserved_without_cwd_guessing(self):
        self.commands[101] = f'codex resume {self.ids[0]}'
        self.rollout(self.ids[1], 99)
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], self.ids)

    def test_duplicate_explicit_identity_is_not_safe_for_restart(self):
        self.commands.update({101:f'codex resume {self.ids[0]}', 201:f'codex resume {self.ids[0]}'})
        self.assertEqual([r['resume_cmd'] for r in detect.discover_agents()], [None, None])

    def test_antigravity_stale_cwd_map_is_not_process_identity(self):
        with patch.object(detect, '_antigravity_sid_from_presence', return_value=None):
            self.assertIsNone(detect.antigravity_sid(self.ids[0], [101]))

    def test_wizard_does_not_generate_unsafe_fresh_restart_without_identity(self):
        for kind in ('codex', 'claude-code', 'antigravity'):
            self.assertEqual(wizard._auto_restart({'kind':kind,'session_id':None}), '')

    def test_nested_worker_does_not_claim_parent_tui_conversation(self):
        self.commands.update({101:'codex resume '+self.ids[0], 8:'codex resume '+self.ids[1]})
        self.ages[8] = 20
        with patch.object(detect,'_proc_table',return_value=(self.commands,{101:[8]})), \
             patch.object(detect,'tmux_sessions',return_value=[{'name':'First','created':self.now-500}]):
            row = detect.discover_agents()[0]
        self.assertEqual(row['session_id'], self.ids[0])
