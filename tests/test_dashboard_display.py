"""Display regressions reported on a live server, 2026-09-01.

1. The SAME model rendered a green tag as a pinned daemon and a grey one as a tmux
   agent, because only daemons fell back to the model name when deriving the vendor.
2. The Session ID column showed "— none" for an agent whose id we do know: it sits in
   the configured resume command.

Both are display-only, but a dashboard that shows the same thing two different ways is
a dashboard people stop trusting.
"""
import sys, os, types, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentsmon import detect, dashboard

SID = "01a05e2f-ebcd-7a22-bd6e-6e0a449f6395"
RESTART = f"codex --dangerously-bypass-approvals-and-sandbox resume {SID}"


class VendorColour(unittest.TestCase):
    def test_model_maps_to_maker(self):
        self.assertEqual(detect.vendor_for_model("GPT-5.6-SOL"), "openai")
        self.assertEqual(detect.vendor_for_model("Claude Opus 5"), "anthropic")
        self.assertEqual(detect.vendor_for_model("Gemini 3.5 Flash"), "google")
        self.assertIsNone(detect.vendor_for_model(None))

    def test_builtin_kind_still_wins(self):
        """A recognised kind keeps its own colour even if the label says otherwise."""
        self.assertEqual(detect.KIND_VENDOR.get("codex"), "openai")
        self.assertEqual(detect.KIND_VENDOR.get("claude-code"), "anthropic")

    def test_same_model_same_colour_daemon_vs_tmux(self):
        """The reported bug: identical model, two different tag colours.

        Both rows now go through vendor_for_agent(), so this fails the moment the two
        paths drift apart again.
        """
        model = "GPT-5.6-SOL"
        daemon = detect.vendor_for_agent(None, model)          # pinned daemon row
        tmux = detect.vendor_for_agent("custom-match", model)  # user-matched tmux row
        self.assertEqual(daemon, tmux)
        self.assertEqual(tmux, "openai")

    def test_unknown_kind_and_unknown_model_stays_uncoloured(self):
        self.assertIsNone(detect.vendor_for_agent("custom-match", "SomeLocalThing"))

    def test_builtin_kind_beats_a_misleading_label(self):
        self.assertEqual(detect.vendor_for_agent("claude-code", "GPT-5.6-SOL"), "anthropic")


class SessionIdFallback(unittest.TestCase):
    def _state(self, discovered):
        cfg = {"agents": [{"name": "Domi - Master", "restart": RESTART, "tag": "GPT-5.6-SOL"}],
               "pinned_daemons": []}
        orig = detect.discover_agents
        detect.discover_agents = lambda *a, **k: discovered
        try:
            return {a["name"]: a for a in dashboard._agents_state(cfg)}
        finally:
            detect.discover_agents = orig

    def test_id_taken_from_resume_when_process_lost_it(self):
        agents = self._state([{"name": "Domi - Master", "kind": "codex", "label": "GPT-5.6-SOL",
                               "session_id": None, "vendor": "openai", "alive": True,
                               "age": 60, "resume_cmd": None, "pids": [1]}])
        self.assertEqual(agents["Domi - Master"]["session_id"], SID)

    def test_detected_id_is_not_overwritten(self):
        jiny = "ffffffff-1111-2222-3333-444444444444"
        agents = self._state([{"name": "Domi - Master", "kind": "codex", "label": "GPT-5.6-SOL",
                               "session_id": jiny, "vendor": "openai", "alive": True,
                               "age": 60, "resume_cmd": None, "pids": [1]}])
        self.assertEqual(agents["Domi - Master"]["session_id"], jiny)

    def test_no_uuid_in_restart_stays_none(self):
        cfg = {"agents": [{"name": "X", "restart": "codex resume"}], "pinned_daemons": []}
        orig = detect.discover_agents
        detect.discover_agents = lambda *a, **k: [{"name": "X", "kind": "codex", "label": "m",
                                                   "session_id": None, "vendor": None, "alive": True,
                                                   "age": 1, "resume_cmd": None, "pids": [1]}]
        try:
            got = {a["name"]: a for a in dashboard._agents_state(cfg)}
        finally:
            detect.discover_agents = orig
        self.assertIsNone(got["X"]["session_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
