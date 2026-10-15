"""Stopping the dashboard must hit exactly the dashboard (2026-09-04): a bare
``pkill -f "agentsmon dashboard"`` also killed the shell script that mentioned it."""
import os, subprocess, sys, tempfile, time, unittest
from unittest.mock import Mock, patch

os.environ.setdefault("AGENTSMON_STATE", tempfile.mkdtemp(prefix="agentsmon-test-state-"))
from agentsmon import dashboard, service  # noqa: E402


class StopDashboard(unittest.TestCase):
    def test_stop_fixture_reaps_both_children(self):
        children=[]; real_popen=subprocess.Popen
        def tracked(*args,**kwargs):
            child=real_popen(*args,**kwargs)
            child.wait=Mock(wraps=child.wait)
            children.append(child)
            return child
        result=unittest.TestResult()
        try:
            with patch.object(subprocess,'Popen',side_effect=tracked):
                StopDashboard('test_pidfile_process_is_stopped_and_a_bystander_mentioning_the_name_survives').run(result)
            self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
            self.assertEqual(len(children),2)
            for child in children:
                self.assertTrue(child.wait.called,'Fixture killed a child without waiting for it')
        finally:
            for child in children:
                if child.poll() is None: child.kill()
                child.wait(timeout=5)

    def test_pidfile_process_is_stopped_and_a_bystander_mentioning_the_name_survives(self):
        victim = subprocess.Popen(["sleep", "30"])
        bystander = subprocess.Popen([sys.executable, "-c", "import time; marker='agentsmon dashboard'; time.sleep(30)"])
        try:
            dashboard.pidfile_path().write_text(str(victim.pid), encoding="utf-8")
            service.stop_dashboard(wait=4)
            time.sleep(0.5)
            self.assertIsNotNone(victim.poll(), "the dashboard process was not stopped")
            self.assertIsNone(bystander.poll(), "a process merely mentioning the dashboard was killed")
        finally:
            for p in (victim, bystander):
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=5)
            dashboard.pidfile_path().unlink(missing_ok=True)

    def test_write_pidfile_records_our_pid(self):
        dashboard.write_pidfile()
        self.assertEqual(int(dashboard.pidfile_path().read_text()), os.getpid())


if __name__ == "__main__":
    unittest.main()


class ActionCsrf(unittest.TestCase):
    """A cross-site form cannot set a custom header; the dashboard page always does (2026-09-05)."""
    def test_action_requires_the_page_header(self):
        from agentsmon import dashboard as d
        self.assertTrue(d._action_allowed({"X-Agentsmon": "action"}))
        self.assertTrue(d._action_allowed({"X-Agentsmon": " Action "}))
        self.assertFalse(d._action_allowed({}))
        self.assertFalse(d._action_allowed({"X-Agentsmon": "yes"}))
