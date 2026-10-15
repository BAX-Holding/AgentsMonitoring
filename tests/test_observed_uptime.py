"""Uptime comes from observed samples, never the count of healthy daily buckets."""
from pathlib import Path
from contextlib import ExitStack
import tempfile
import unittest
from unittest.mock import patch

from agentsmon import config, dashboard, db


class ObservedUptime(unittest.TestCase):
    def setUp(self):
        stack=ExitStack(); self.addCleanup(stack.close)
        tmp=stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(patch.object(config,'state_dir',return_value=Path(tmp)))
        self.now=1700000120
        stack.enter_context(patch.object(db.time,'time',return_value=self.now))
        self.cfg={'services':[{'name':'Fresh'}],
                  'probe':{'sla_window_days':90,'timeline_days':90,'min_outage_samples':3}}

    def test_two_samples_are_two_minutes_even_with_one_green_day(self):
        db.record('Fresh',True,ts=self.now-120)
        db.record('Fresh',True,ts=self.now)
        card=dashboard._service_state(self.cfg)[0]
        self.assertEqual(card['sla_samples'],2)
        self.assertEqual(sum(b['uptime_pct']==100 for b in card['timeline']),1)
        self.assertEqual(card['uptime_seconds'],120)

    def test_no_observation_is_unknown_first_observation_is_zero(self):
        self.assertIsNone(dashboard._service_state(self.cfg)[0]['uptime_seconds'])
        db.record('Fresh',True,ts=self.now)
        self.assertEqual(dashboard._service_state(self.cfg)[0]['uptime_seconds'],0)

    def test_confirmed_outage_resets_streak_short_blip_does_not(self):
        for offset,up in ((600,True),(540,False),(480,True)):
            db.record('Fresh',up,ts=self.now-offset)
        self.assertEqual(db.uptime_seconds('Fresh'),600)
        for offset in (240,180,120):
            db.record('Fresh',False,ts=self.now-offset)
        self.assertEqual(db.uptime_seconds('Fresh'),0)
        db.record('Fresh',True,ts=self.now-60)
        self.assertEqual(db.uptime_seconds('Fresh'),60)
