"""The Claude model must be found even when large records follow the last assistant turn."""
import json
import tempfile
import unittest
from pathlib import Path

from agentsmon import detect


class ClaudeModelWindow(unittest.TestCase):
    def test_model_before_a_large_tail_is_still_found(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'session.jsonl'
            lines = [json.dumps({'type': 'assistant', 'message': {'model': 'claude-opus-5-5'}}),
                     json.dumps({'type': 'attachment', 'content': 'x' * 200_000})]
            path.write_text('\n'.join(lines) + '\n')
            self.assertEqual(detect._claude_model_from_transcript(str(path)), 'Opus 5.5')

    def test_no_model_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'session.jsonl'
            path.write_text(json.dumps({'type': 'user', 'content': 'y' * 100_000}) + '\n')
            self.assertIsNone(detect._claude_model_from_transcript(str(path)))


if __name__ == '__main__':
    unittest.main()
