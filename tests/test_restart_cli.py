"""`agentsmon restart` reuses the dashboard restart for configured agents."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from agentsmon import __main__ as cli, config, dashboard, detect, restarter


CFG = {'agents': [{'name': 'Codex'}, {'name': 'Claude'}, {'name': 'Off', 'enabled': False}]}


class RestartCli(unittest.TestCase):
    def _run(self, argv, running=('Codex', 'Claude', 'Off')):
        alive = [{'name': n, 'alive': True} for n in running]
        with patch.object(config, 'load', return_value=CFG), \
             patch.object(detect, 'discover_agents', return_value=alive), \
             patch.object(dashboard, '_agent_action', return_value=(True, 'restarting')) as act, \
             redirect_stdout(io.StringIO()) as out:
            rc = cli.main(argv)
        return rc, [c.args for c in act.call_args_list], out.getvalue()

    def test_all_restarts_only_running_enabled_agents(self):
        rc, calls, _ = self._run(['restart', '--all'], running=('Codex',))
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [('Codex', 'restart')])

    def test_named_agent_is_restarted_and_unknown_is_refused(self):
        rc, calls, _ = self._run(['restart', 'Claude'])
        self.assertEqual((rc, calls), (0, [('Claude', 'restart')]))
        rc, calls, out = self._run(['restart', 'Nope'])
        self.assertEqual((rc, calls), (1, []))
        self.assertIn('Unknown agent', out)


if __name__ == '__main__':
    unittest.main()
