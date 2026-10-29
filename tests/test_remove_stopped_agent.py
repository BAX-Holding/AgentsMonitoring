"""Second ✕ on a stopped agent removes its monitoring entry; first ✕ only stops it."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentsmon import config, dashboard


class RemoveStoppedAgent(unittest.TestCase):
    def _run(self, agents, has_session_rc):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.json'
            path.write_text(json.dumps({'agents': agents, 'daemons': []}))
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                rc = has_session_rc if argv[1:2] == ['has-session'] else 0
                return subprocess.CompletedProcess(argv, rc, '', '')
            with patch.object(config, 'DEFAULT_PATH', path), \
                 patch.object(config, 'load', return_value={'agents': agents, 'daemons': []}), \
                 patch.object(dashboard.subprocess, 'run', side_effect=run):
                ok, message = dashboard._agent_action('Helper', 'stop')
            return ok, message, json.loads(path.read_text()), calls

    def test_stopped_agent_without_session_is_removed(self):
        ok, message, saved, _ = self._run(
            [{'name': 'Helper', 'enabled': False}, {'name': 'Other'}], has_session_rc=1)
        self.assertTrue(ok, message)
        self.assertIn('removed', message)
        self.assertEqual([a['name'] for a in saved['agents']], ['Other'])

    def test_running_agent_is_only_stopped(self):
        ok, message, saved, calls = self._run([{'name': 'Helper'}], has_session_rc=0)
        self.assertTrue(ok, message)
        self.assertEqual(saved['agents'], [{'name': 'Helper', 'enabled': False}])
        self.assertIn('kill-session', [c[1] for c in calls if len(c) > 1])


if __name__ == '__main__':
    unittest.main()
