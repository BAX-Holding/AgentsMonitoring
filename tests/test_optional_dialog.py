import unittest
from unittest.mock import patch
from agentsmon import dialogs


class OptionalDialog(unittest.TestCase):
    TEXT = 'Try the new fullscreen renderer?\n❯ 1. Yes\n  2. Not now\nEnter to confirm · Esc to cancel\n'
    REAL = '''  Try the new fullscreen renderer?
  · Flicker-free output — fixes the flashing you see during long responses
  · Mouse support — click to move your cursor or expand results
  · Selected text auto-copies to your clipboard
  ❯ 1. Yes, try it
    2. Not now
  Enter to confirm · Esc to cancel
'''

    def test_real_dialog_with_history_and_bullets_is_declined(self):
        from subprocess import CompletedProcess
        screen = 'Previous session output.\nTask completed.\n\n'+self.REAL
        self.assertTrue(dialogs.optional_renderer_dialog(screen))
        with patch.object(dialogs.detect,'_run',side_effect=[CompletedProcess([],0,screen,''),
                CompletedProcess([],0,'','')]) as run:
            self.assertTrue(dialogs.dismiss_optional_renderer('Example'))
        self.assertEqual(run.call_args.args[0][-2:],['2','Enter'])

    def test_old_or_quoted_dialog_cannot_hide_a_later_permission_prompt(self):
        for text in (self.REAL+'Allow tool access?\n1. Yes\n2. No',
                     self.REAL+'Log in to continue', self.REAL+'Trust this folder?\n',
                     '\n'.join('> '+line for line in self.REAL.splitlines()),
                     self.REAL+'\n'.join(['other output']*16)):
            self.assertFalse(dialogs.optional_renderer_dialog(text))

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
