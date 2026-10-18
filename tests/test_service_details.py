"""Opt-in visible probe details, without product-specific renderer branches."""
from unittest import TestCase
from unittest.mock import patch
from agentsmon import dashboard


class ServiceDetails(TestCase):
    def test_details_explicit_boolean_only(self):
        with patch.object(dashboard.db,'last',return_value=None), \
             patch.object(dashboard.db,'sla',return_value=(None,0)), \
             patch.object(dashboard.db,'avg_latency',return_value=None), \
             patch.object(dashboard.db,'uptime_seconds',return_value=None), \
             patch.object(dashboard.db,'timeline',return_value=[]), \
             patch.object(dashboard,'_service_rows',return_value=[]):
            for value in (True,False,None,'false'):
                state=dashboard._service_state({'services':[{'name':'Fixture','row_details':value}]},0)[0]
                self.assertIs(state['row_details'],value is True)
