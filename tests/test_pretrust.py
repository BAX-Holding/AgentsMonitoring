"""Claude Code must not stop on its first-run prompts when it is launched detached into tmux.

Live case 2026-09-03: `agentsmon new` created a Claude agent on a freshly installed server, but
the agent sat on "Is this a project you created or one you trust?" and never appeared on the
dashboard. Each test names the mutation that turns it red.
"""
import json
import tempfile
import unittest
from pathlib import Path

from agentsmon.wizard import pretrust_claude


class FirstRunPromptsArePreAnswered(unittest.TestCase):
    def test_records_trust_and_onboarding_on_an_empty_home(self):
        """Mutation: drop the `hasTrustDialogAccepted` assignment → the dialog still blocks."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            zapsano = pretrust_claude("/home/domi", home)
            cfg = json.loads((home / ".claude.json").read_text("utf-8"))
            self.assertTrue(cfg["projects"]["/home/domi"]["hasTrustDialogAccepted"])
            self.assertTrue(cfg["hasCompletedOnboarding"])
            self.assertIn("trusted folder /home/domi", zapsano)

    def test_keeps_everything_else_in_the_config(self):
        """Mutation: write a fresh dict instead of the parsed one → the user loses their config."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".claude.json").write_text(json.dumps({
                "numStartups": 103, "customApiKeyResponses": {"approved": ["abc"]},
                "projects": {"/jiny": {"hasTrustDialogAccepted": True, "lastCost": 1.5}}}), "utf-8")
            pretrust_claude("/home/domi", home)
            cfg = json.loads((home / ".claude.json").read_text("utf-8"))
            self.assertEqual(cfg["numStartups"], 103)
            self.assertEqual(cfg["customApiKeyResponses"], {"approved": ["abc"]})
            self.assertEqual(cfg["projects"]["/jiny"]["lastCost"], 1.5)
            self.assertTrue(cfg["projects"]["/home/domi"]["hasTrustDialogAccepted"])

    def test_is_a_no_op_when_already_trusted(self):
        """Nothing to record → the file must not be touched at all. Written in COMPACT json on
        purpose: a needless rewrite would reformat it to indent=2, so byte equality is what proves
        the write was skipped (comparing the parsed value would pass either way).

        Mutation: drop the `if not zapsano: return ""` guard → the config is rewritten."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            puvodni = '{"hasCompletedOnboarding":true,"projects":{"/home/domi":{"hasTrustDialogAccepted":true}}}'
            (home / ".claude.json").write_text(puvodni, "utf-8")
            self.assertEqual(pretrust_claude("/home/domi", home), "")
            self.assertEqual((home / ".claude.json").read_text("utf-8"), puvodni,
                             "the config was rewritten even though nothing changed")

    def test_never_overwrites_a_config_it_cannot_parse(self):
        """A corrupt or half-written config must be left alone — rewriting it would lock the user
        out of Claude entirely.

        Mutation: treat a parse error as an empty dict → the file is replaced with `{...}`."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".claude.json").write_text("{ this is not json", "utf-8")
            self.assertEqual(pretrust_claude("/home/domi", home), "")
            self.assertEqual((home / ".claude.json").read_text("utf-8"), "{ this is not json")

    def test_config_is_owner_only(self):
        """The file holds API-key approvals and project history.

        Mutation: drop the chmod → it inherits the umask and can be world-readable."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            pretrust_claude("/home/domi", home)
            self.assertEqual((home / ".claude.json").stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
