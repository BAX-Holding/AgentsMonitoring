"""Session identity must belong to a process, never just to its working directory."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import detect, identity, wizard


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

    def single(self):
        return patch.object(detect, 'tmux_sessions', return_value=[
            {'name':'First', 'created':self.now-500}])

    def test_single_continue_claude_uses_old_transcript_model_and_pins_resume(self):
        self.commands[101] = 'claude --continue'
        self.rollout(self.ids[1], 3000, 'claude')
        path = self.rollout(self.ids[0], 1000, 'claude')
        with path.open('a') as stream:
            stream.write(json.dumps({'type':'assistant','message':{'model':'claude-opus-5-5'}})+'\n')
        os.utime(path, (self.now-900, self.now-900))
        with self.single():
            row = detect.discover_agents()[0]
        self.assertEqual(row['session_id'], self.ids[0])
        self.assertEqual(row['label'], 'Opus 5.5')
        agent = {'name':'First','kind':'claude-code','cwd':'/work/shared',
                 'restart':'claude --continue'}
        with patch.object(identity, 'requires_pin', return_value=True), \
             patch('agentsmon.config.state_dir', return_value=self.home/'state'):
            pins = identity.pin_sessions({'agents':[agent]}, [row])
        resumed = identity.safe_restart(agent, [], pins)
        self.assertIn('--resume '+self.ids[0], resumed['restart'])
        self.assertNotIn('--continue', resumed['restart'])
        self.assertNotIn('restart_warning', resumed)

    def test_single_codex_uses_latest_old_rollout_and_its_model(self):
        self.commands[101] = 'codex resume --last'
        path = self.rollout(self.ids[0], 1000)
        with path.open('a') as stream:
            stream.write(json.dumps({'type':'turn_context','payload':{'model':'gpt-5.5'}})+'\n')
        os.utime(path, (self.now-900, self.now-900))
        with self.single():
            row = detect.discover_agents()[0]
        self.assertEqual(row['session_id'], self.ids[0])
        self.assertEqual(row['label'], 'GPT-5.5')
        self.assertIn(self.ids[0], row['resume_cmd'])

    def agy_map(self):
        folder = self.home/'.gemini/antigravity-cli/cache'
        folder.mkdir(parents=True)
        (folder/'last_conversations.json').write_text(json.dumps({'/work/shared':self.ids[0]}))

    def test_single_antigravity_uses_workspace_map(self):
        self.commands[101] = 'agy'
        self.agy_map()
        with self.single():
            row = detect.discover_agents()[0]
        self.assertEqual(row['session_id'], self.ids[0])
        self.assertIn(self.ids[0], row['resume_cmd'])

    def test_two_claude_continue_agents_do_not_guess_old_transcripts(self):
        self.commands.update({101:'claude --continue',201:'claude --continue'})
        self.rollout(self.ids[0], 1000, 'claude')
        self.rollout(self.ids[1], 2000, 'claude')
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], [None, None])

    def test_two_antigravity_agents_do_not_share_workspace_map(self):
        self.commands.update({101:'agy',201:'agy'})
        self.agy_map()
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], [None, None])

    def test_other_kind_in_same_directory_does_not_block_singleton(self):
        self.commands.update({101:'claude --continue',201:'codex'})
        self.rollout(self.ids[0], 1000, 'claude')
        self.rollout(self.ids[1], 2000)
        self.assertEqual([r['session_id'] for r in detect.discover_agents()], self.ids)

    def test_latest_identity_claimed_elsewhere_is_not_replaced_by_older_guess(self):
        self.commands.update({101:'claude --continue',201:'claude --resume '+self.ids[0]})
        self.rollout(self.ids[0], 1000, 'claude')
        self.rollout(self.ids[1], 2000, 'claude')
        with patch.object(detect, '_session_cwd', side_effect=lambda name:
                          '/work/shared' if name=='First' else '/work/other'):
            rows = detect.discover_agents()
        self.assertIsNone(rows[0]['session_id'])
        self.assertEqual(rows[1]['session_id'], self.ids[0])

    def test_explicit_identity_wins_over_latest_singleton_transcript(self):
        self.commands[101] = 'claude --resume '+self.ids[0]
        self.rollout(self.ids[1], 1000, 'claude')
        with self.single():
            self.assertEqual(detect.discover_agents()[0]['session_id'], self.ids[0])

    def test_single_codex_respects_custom_home(self):
        source = self.rollout(self.ids[0], 1000)
        target = self.home/'alternate/sessions'/source.name
        target.parent.mkdir(parents=True)
        source.replace(target)
        with self.single(), patch.dict(os.environ, {'CODEX_HOME':str(target.parent.parent)}):
            self.assertEqual(detect.discover_agents()[0]['session_id'], self.ids[0])

    def test_single_claude_startup_record_without_cwd_or_timestamp(self):
        self.commands[101] = 'claude --continue'
        path = self.rollout(self.ids[0], 1000, 'claude')
        path.write_text(json.dumps({'type':'file-history-snapshot','sessionId':self.ids[0]})+'\n')
        with self.single():
            self.assertEqual(detect.discover_agents()[0]['session_id'], self.ids[0])

    def test_singleton_workspace_maps_cannot_claim_same_id_twice(self):
        self.commands.update({101:'agy',201:'agy'})
        with patch.object(detect, '_session_cwd', side_effect=lambda name:'/work/'+name), \
             patch.object(detect, '_antigravity_info_for_cwd', return_value=(self.ids[0],None)):
            self.assertEqual([r['session_id'] for r in detect.discover_agents()], [None, None])
