import unittest
from unittest.mock import patch
from agentsmon import dialogs


class OptionalDialog(unittest.TestCase):
    TEXT = 'Try the new fullscreen renderer?\n❯ 1. Yes\n  2. Not now\n'

    def test_exact_optional_dialog_is_recognized(self):
        self.assertTrue(dialogs.optional_renderer_dialog(self.TEXT))

    def test_security_prompts_and_conversation_quotes_are_never_answered(self):
        for text in ('Allow access?\n1. Yes\n2. No', 'Log in\n1. Yes',
                     'Assistant says:\n'+self.TEXT, self.TEXT+'Allow tool access?'):
            self.assertFalse(dialogs.optional_renderer_dialog(text))

    def test_unrecognized_screen_does_not_send_keys(self):
        from subprocess import CompletedProcess
        with patch.object(dialogs.detect,'_run',return_value=CompletedProcess([],0,'normal conversation','')) as run:
            self.assertFalse(dialogs.dismiss_optional_renderer('Example'))
        self.assertEqual(run.call_count, 1)
