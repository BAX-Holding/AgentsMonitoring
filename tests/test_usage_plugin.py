import json
from pathlib import Path
import tempfile
import time
import unittest
from agentsmon import usage_plugin as usage


class AccountUsage(unittest.TestCase):
    def test_accounts_never_share_by_vendor_missing_source_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'status.json'
            p.write_text(json.dumps({'rate_limits':{'five_hour':{'used_percentage':20,'resets_at':time.time()+3000}}}))
            result=usage.collect({}, {'sources':{'Alice':{'path':str(p),'format':'claude-statusline','account':'A'},
                                                'Bob':{'path':str(p)+'-missing','format':'claude-statusline','account':'B'}}})
            self.assertEqual(result['patches'][0]['cells']['limits']['bars'][0]['percent'],20)
            self.assertEqual(result['patches'][1]['cells']['limits']['text'],'Unavailable')

    def test_expired_negative_nan_and_percentage_above_100_do_not_fake_a_limit(self):
        for pct in (-1,101,float('nan'),True,'90'):
            self.assertIsNone(usage.window('5h',pct,300,100))
        self.assertIsNone(usage.window('5h',30,99,100))
        self.assertEqual(usage.window('5h',30,'2030-01-01T00:00:00Z',100)['percent'],30)

    def test_rollout_tail_and_real_window_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rollout.jsonl'
            p.write_text(json.dumps({'timestamp':'2026-10-15T12:00:00Z','payload':{'rate_limits':{
                'primary':{'used_percent':42,'window_minutes':180,'resets_at':2_000_000_000}}}})+'\n')
            result=usage.read_source({'path':str(p),'format':'codex-rollout'},1_800_000_000)
            self.assertEqual(result['bars'][0]['label'],'3h')
