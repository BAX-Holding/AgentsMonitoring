"""2026-09-12: the dashboard died with 'Too many open files' — sqlite connections were committed but
never closed. Every db helper must leave the number of open file descriptors unchanged."""
import os, sys, tempfile, unittest
import sqlite3
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agentsmon import db, config  # noqa: E402


def _open_fds() -> int:
    return len(os.listdir("/dev/fd"))


class NoFdLeak(unittest.TestCase):
    def test_connection_is_closed_when_initialization_fails(self):
        connection=MagicMock()
        connection.execute.side_effect=sqlite3.OperationalError('fixture')
        with patch.object(db.sqlite3,'connect',return_value=connection),patch.object(db,'_path',return_value=':memory:'):
            with self.assertRaises(sqlite3.OperationalError): db.record('fixture',True)
        connection.close.assert_called_once()

    def test_antigravity_failed_query_closes_both_attempts(self):
        from agentsmon import detect
        from pathlib import Path
        first,second=MagicMock(),MagicMock()
        for c in (first,second): c.execute.side_effect=sqlite3.OperationalError('fixture')
        with patch.object(Path,'exists',return_value=True),patch.object(detect.sqlite3,'connect',side_effect=[first,second]):
            self.assertIsNone(detect._antigravity_model_from_db('fixture'))
        first.close.assert_called_once();second.close.assert_called_once()

    def test_probe_helpers_do_not_leak_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = config.state_dir
            config.state_dir = lambda: __import__("pathlib").Path(tmp)
            try:
                db.record("svc", True, 0.1)
                before = _open_fds()
                for _ in range(200):
                    db.record("svc", True, 0.1)
                    db.last("svc"); db.sla("svc", 3600); db.avg_latency("svc", 3600); db.uptime_seconds("svc")
                after = _open_fds()
            finally:
                config.state_dir = orig
        self.assertLessEqual(after - before, 2, f"file descriptors grew from {before} to {after}")


if __name__ == "__main__":
    unittest.main()
